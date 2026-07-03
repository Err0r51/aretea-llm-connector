# PRD 3: CI/CD & continuous deployment for the Drive connector v1

> **Status:** Active — Last refreshed: 2026-07-03

_Follows PRD 2 (`prd_01_…`, the read-only connector). That PRD delivered the service; this one
delivers the pipeline that **ships, health-checks, versions, and rolls back** that service. The
*how* (workflow YAML, health snippet, release config, rollback runbook) will live in
`docs/ARCHITECTURE.md`; this PRD is the *what/why* + governance. Header is "PRD 3" continuing the
sequence (the root `prd-1` draft = 1, `prd_01_…` file = "PRD 2")._

## Problem

The connector reaches production by hand. Tests (`ruff` / `mypy --strict` / `pytest`) run only on a
developer's machine, so a change that fails them can still land on `main` and be shipped — nothing
gates the release. Once deployed there is **no way to answer "what is running right now"**: the
version (`0.1.0`) is hand-duplicated in `pyproject.toml` and `aretea_drive_mcp/__init__.py`, exposed
nowhere at runtime, and never tagged. There is **no health signal** (no `/health`; Railway treats a
container that merely started listening as "up," even if the app is broken) and **no defined
rollback** — recovering a bad deploy is ad-hoc. The Railway service still reports builder `RAILPACK`,
so the repo's committed `railway.json` (Dockerfile builder, EU region, restart policy) is not even in
effect. This is the **first of several connectors**; the release pattern set here is reused, so it
must be automated, gated, and recoverable — not bespoke per service.

## Goals

- **Merge to a green `main` auto-deploys** to Railway EU with no manual step.
- **CI gates the deploy**: `ruff` + `mypy --strict` + unit `pytest` run on GitHub runners; a failing
  run leaves the deploy un-shipped, and the same checks are required to merge.
- **The running build is identifiable**: an unauthenticated `GET /health` returns 200 with the
  deployed commit SHA (+ an in-source floor version).
- **Every release is semantically versioned** — a `vX.Y.Z` git tag + GitHub Release derived
  automatically from Conventional Commits.
- **A bad release is recoverable** via a documented one-click rollback to a prior Railway deployment,
  with a way to confirm which version is live.
- The pipeline is **reusable by the next connector** without re-solving CI, release, or rollback.

## Non-Goals

- **Zero-downtime / blue-green / canary deploys.** The single attached volume makes two concurrent
  deployments impossible (Railway prevents it to avoid data corruption), so every deploy has a brief
  downtime window and drops in-memory MCP sessions — accepted for an internal connector. → later
  "stateless / HA" PRD.
- **Automatic rollback on runtime failure**, usage dashboards, alerting, uptime monitoring. Health is
  checked at deploy time only; ongoing monitoring is deferred. → PRD "monitoring" (inherited from
  PRD 2's Non-Goals).
- **Integration / e2e tests and the claude.ai-web smoke test _in CI_.** They need real Google
  credentials and a browser OAuth flow; per the repo policy ("test against the real API or don't
  write the test") they stay **manual / local**, owned by PRD 2's phasing. No mocked smoke tests.
- **Multi-Python test matrix, PyPI publishing, a container registry.** Out of scope for one internal
  service; Railway builds the Dockerfile directly.
- **A deploy-approval / staging environment.** v1 is continuous deployment straight to the single
  prod service. → backlog if a staging need appears.

## Design

### Decisions (locked)

- **CD transport = Railway native GitHub connect + "Wait for CI" (token-free).** Railway's GitHub App
  watches `main`; with **Wait for CI** enabled the deploy holds in `WAITING` until the push workflow
  succeeds (`SKIPPED` if it fails). No deploy step runs in GitHub Actions and **no `RAILWAY_TOKEN`**
  lives in GitHub secrets — one fewer long-lived production credential, which matters for a security
  shop. Requires the Railway GitHub App to have repo access + accepted permissions.
- **CI = GitHub Actions on GH runners.** One workflow with `on: push: branches: [main]` (required for
  Wait for CI) **and** `on: pull_request` (for branch protection): `ruff check`, `mypy --strict`,
  `pytest` (the existing unit tests), plus a no-push `docker build` to catch Dockerfile breakage
  before Railway does. Secret-free.
- **Merge gate = branch protection** with those checks required, so `main` is always deployable and
  every deploy corresponds to a reviewed, green commit.
- **Health = a FastMCP `custom_route`, not a wrapper app.** Add `@mcp.custom_route("/health",
  methods=["GET"])` on the FastMCP app; a parent Starlette/FastAPI wrapper is **forbidden** — it
  shadows `http_app`'s session-manager lifespan (`ARCHITECTURE §9`, python-sdk #1367). Unauthenticated;
  returns `{status, commit, version, region}`; must accept the `healthcheck.railway.app` hostname. It
  reports **"up," not "Drive works"** — it does **not** call the Google API (flaky, rate-limited).
  Wired as `healthcheckPath` in `railway.json`.
- **Health layering (state explicitly):** fail-fast config at boot (bad/missing secrets → container
  never starts) → `/health` (process up + config loaded) → **manual** post-deploy Drive-read smoke
  test on claude.ai web. Each catches a different failure class.
- **Version identity = the deployed commit SHA.** `RAILWAY_GIT_COMMIT_SHA` is injected by native
  connect (build + runtime, guaranteed) and surfaced at `/health`. The **literal `vX.Y.Z` string is
  not surfaced in-container** — `.dockerignore` excludes `.git` (no `git describe`) and Railway
  exposes no tag build-var — so the tag/Release is the **human-facing label, mapped from the SHA on
  GitHub**. The hardcoded `__version__` is removed; `pyproject.toml` keeps a floor version read via
  `importlib.metadata`.
- **Release automation = tag-only.** `python-semantic-release` (or equivalent) derives the next
  SemVer from Conventional Commits and creates the `vX.Y.Z` **tag + GitHub Release only — no
  write-back commit to source.** *This no-write-back rule is the load-bearing invariant:* a write-back
  would push a second commit and cause a double deploy under native autodeploy. Runs on `push` to
  `main` only (not PRs). The history already uses `feat:` / `fix:` / `docs:` prefixes, so no new
  commit discipline is introduced.
- **Rollback = manual redeploy of the last-good Railway deployment** (retained by Railway, no
  rebuild), via a documented runbook. Caveats to record: (a) rolling back **code does not revert
  env-var / secret changes**; (b) a change to the on-disk storage format (FastMCP token store on the
  volume) can break rollback — any format change needs a migration + compatibility note, and
  `init_db` must stay idempotent and forward/backward-compatible.

**(PENDING SPIKE) FastMCP `custom_route` auth bypass.** The `/health` route must be reachable
**without** an OAuth bearer token and must not trip the `AuditMiddleware` gate. Confirm on FastMCP
3.4.2 that `custom_route` registers outside the auth/middleware chain (or find the documented way to
mark it public) before relying on it as Railway's `healthcheckPath`. If it cannot be made public, the
healthcheck path/port needs an alternate exposure.

### Design details

Full pipeline mechanics — the workflow YAML, the `custom_route` health handler, the
`python-semantic-release` config and its no-write-back settings, the `railway.json`
`healthcheckPath`, and the rollback runbook — will be added to `docs/ARCHITECTURE.md` during
implementation. Summary of the request/release path:

- **PR:** open → GH Actions (`ruff`, `mypy --strict`, `pytest`, `docker build`) → branch protection
  requires green → merge.
- **Release:** push to `main` → GH Actions runs (same checks) + `python-semantic-release` cuts the
  tag + GitHub Release → Railway (native connect, Wait for CI) sees the checks pass → builds the
  Dockerfile → probes `/health` → routes traffic (brief downtime as the volume re-mounts).
- **Runtime identity:** `/health` reports `RAILWAY_GIT_COMMIT_SHA`; that SHA maps 1:1 to the GitHub
  Release / tag, giving "what's live == what was released."
- **Rollback:** operator selects the prior deployment in Railway → redeploy (no rebuild) → confirm
  `/health` reports the previous SHA.

## Phasing

Gate-first — prove the CI gate and health signal before wiring auto-deploy.

1. **Phase 0 — Foundations.** Add the `/health` `custom_route` (SHA + floor version); remove the
   hardcoded `__version__`; commit `railway.json` with `healthcheckPath` and confirm the service
   builder flips `RAILPACK → DOCKERFILE`. _Exit:_ `/health` returns 200 locally with SHA + version.
2. **Phase 1 — CI.** Workflow (`push:[main]` + `pull_request`) running `ruff` / `mypy` / `pytest` /
   `docker build`; enable branch protection with those checks required. _Exit:_ a red PR is blocked;
   a green PR is mergeable.
3. **Phase 2 — CD (native connect + Wait for CI).** Connect the repo via the Railway GitHub App,
   set trigger branch `main`, enable Wait for CI; healthcheck gates go-live. _Exit:_ a green merge
   produces a single live deploy with zero manual steps; a red push leaves the deploy `SKIPPED`.
4. **Phase 3 — Automated SemVer (tag-only).** Add `python-semantic-release` (tag + Release only, no
   write-back, `push:[main]` only). _Exit:_ a `feat:` merge auto-creates the next minor tag +
   Release; `/health` SHA maps to it.
5. **Phase 4 — Rollback + notifications.** Write and rehearse the rollback runbook; optionally add a
   deploy-status notification. _Exit:_ a rollback restores the prior deployment, verified via
   `/health` reporting the previous SHA.

## Success criteria / Metrics

- **Primary:** a normal change goes PR → green CI → merge → live, versioned deploy with **no manual
  command**. Baseline today: fully manual, ungated.
- **Guardrail:** a change that fails `ruff` / `mypy` / `pytest` **cannot** reach a production deploy
  (blocked at merge and, redundantly, left `SKIPPED` by Wait for CI). Baseline must be: 0 red deploys.
- **Traceability:** the `/health` SHA equals the commit of the deployed GitHub Release — "what's live
  == what was released" is answerable at any time.

## Observability

- `GET /health` → 200 with `{status, commit (SHA), version (floor), region}`. Deploy-time only;
  Railway does not poll it continuously.
- Deploy status is visible via Railway deployment history + GitHub Actions run status; an optional
  deploy-succeeded/failed notification (channel TBD) may be added in Phase 4.
- No app-usage dashboards or alerting (deferred, per Non-Goals).

## Acceptance criteria

- [ ] **AC1** — Given a PR whose `ruff` / `mypy` / `pytest` run fails, When a merge to `main` is
      attempted, Then branch protection blocks the merge. _(test: e2e)_
- [ ] **AC2** — Given a green merge to `main`, When the pipeline runs, Then Railway rebuilds from the
      Dockerfile and the new version goes live with no manual step. _(test: e2e)_
- [ ] **AC3** — Given the deployed service, When `GET /health` is called without a bearer token, Then
      it returns 200 with the deployed commit SHA and the `pyproject` floor version. _(test: integration)_
- [ ] **AC4** — Given a new deployment that never returns 200 from `/health`, When Railway probes it,
      Then that deployment is not routed traffic and is marked failed. _(test: integration)_
- [ ] **AC5** — Given a push to `main` whose GitHub Actions run fails, When Wait for CI evaluates it,
      Then the Railway deploy is left `SKIPPED` (never built/live). _(test: e2e)_
- [ ] **AC6** — Given Conventional-commit merges since the last release, When `main` is deployed, Then
      the correct `vX.Y.Z` tag + GitHub Release is created **with no write-back commit to source**.
      _(test: e2e)_
- [ ] **AC7** — Given a bad release is live, When the operator follows the rollback runbook, Then the
      previous Railway deployment is restored and `/health` reports the prior SHA. _(test: e2e — manual drill)_
- [ ] **AC8** — Given a live deployment, When its `/health` SHA is compared to the GitHub Release cut
      for that commit, Then they match (live == released). _(test: integration)_
- [ ] **AC9** — Given a single merge to `main`, When deployment history is inspected, Then exactly one
      deploy fired (no double-deploy from a version write-back). _(test: integration)_
- [ ] **AC10** — Given the codebase, When the version constant is inspected, Then the duplicated
      hardcoded `__version__` is gone and the single in-source floor is read via `importlib.metadata`.
      _(test: unit)_

## Open questions

- **Deploy notifications** (owner: Frederik) — in-scope here or in the deferred monitoring PRD? which
  channel (Slack / email)?
- **Railway GitHub App** (owner: Frederik) — who connects the repo and accepts the updated
  permissions so the Wait for CI flag becomes available.
- **`custom_route` auth bypass** — resolved by the Phase-0 spike (see `(PENDING SPIKE)` above);
  determines whether `/health` can be the `healthcheckPath` as designed.
- **Live-service reconfiguration** (owner: Frederik) — confirm connecting the repo and flipping the
  running service `RAILPACK → DOCKERFILE` (committing `railway.json`) is safe on the live service.
- **Deploy-window policy** (owner: Frederik) — since every deploy drops in-memory MCP sessions, deploy
  anytime vs. off-hours guidance.
- **Tag-at-runtime** — surfacing the literal `vX.Y.Z` string in-container is deferred as
  `(PENDING SPIKE)`; SHA-based identity stands in the meantime. Do not treat it as a requirement
  until confirmed feasible.

## References

- `prd_01_aretea_drive_mcp_connector_read_only_v1.md` — the connector this pipeline ships.
- `docs/ARCHITECTURE.md` — `§9` (lifespan / why `http_app` is unwrapped); deployment section (to be
  extended with the CI/CD mechanics).
- Railway docs — Healthchecks ("small amount of downtime … volume attached, even with a healthcheck
  endpoint configured"), Controlling GitHub Autodeploys / **Wait for CI**.
