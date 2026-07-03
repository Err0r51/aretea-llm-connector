# Aretea Drive MCP Connector — Architecture (v1, read-only)

`Status:` Draft · `Derived from:` [`prd_01`](prd_01_aretea_drive_mcp_connector_read_only_v1.md) · `Last updated:` 2 July 2026

The *what/why* live in the PRD. This is the *how*: the module contracts, data model, request
path, and failure behavior an implementer builds against. Product governance (sign-off gates,
phasing, acceptance matrix, non-goals) stays in the PRD, not here.

**Confidence.** Facts below are grounded in current library docs. The wiring compiles against real
FastMCP 3.4.2 (the app assembles; unknown kwargs would fail import), but *compiles* is not *works* —
the load-bearing behavior (the claude.ai web OAuth flow, real Drive reads) is proven only by the
Phase-1 spike against live services, not by anything in this repo. Items that can only be settled
live stay ⚠ inline.

## Testing principle

**Test against the real API, or don't write the test.** Mocking Google/OAuth and asserting success
only proves the mock matches our assumptions — it is negative-value assurance (it turns green when
the real integration is broken). So:

- **Unit tests cover *our own* invariants only** — logic that is ours, with no external call to fake:
  the driveId equality wall, the no-delegation assertion, the 3-scope construction, output
  truncation, the email-domain suffix check, and that only read tools are registered. These need no
  network and are genuinely useful.
- **Integration tests hit real services** — Drive/Sheets/Slides against a dedicated **test Shared
  Drive** (its own throwaway corpus + a known out-of-drive file for the FR5 negative), and the OAuth
  flow against a **test Google Workspace client**, run in the spike and in CI with real credentials.
- **We do not add mocked "integration" tests** to make the AC matrix look green. An AC that needs a
  live service stays visibly un-covered until it is tested live. No smoke test stands in for that.

**Connector URL.** The PRM `resource` is `<PUBLIC_SERVER_URL>/mcp` (PRM path
`/.well-known/oauth-protected-resource/mcp`), so the URL the Owner enters in claude.ai must include
the **`/mcp`** path — confirm this live in the spike (a mismatch is a classic "works in Code, fails
on web" failure).

---

## 1. The one idea: two decoupled hops

- **Client hop** (claude.ai ↔ our server): OAuth 2.1. Establishes *who* (identity → audit + org
  gate). Grants **zero Google Drive access**.
- **Drive hop** (our server ↔ Google): one fixed **service account**, used inside tool execution.
  **No domain-wide delegation, no impersonation.** Reads only what its **Shared-Drive membership**
  allows — shared across all users (accepted all-or-nothing data model).

The data boundary is *service-account membership*. Identity is for **attribution + org gating only**,
never to scope Drive data.

```
claude.ai (web) ──client hop: OAuth 2.1 (PKCE, DCR)──▶ FastMCP server (Railway EU-West)
                                                          │  GoogleProvider  → Google OIDC (openid email profile, NO Drive)
                                                          │  toolsets/drive  → service-account creds (3 read scopes, no DWD)
                                                          │  audit middleware → Railway logs (per-user JSON)
                                                          ▼
                                              Drive v3 / Sheets v4 / Slides v1
                                              corpora=drive, driveId=<AI-Visible ONLY>
```

---

## 2. Client hop — auth contract

**Provider:** FastMCP `GoogleProvider` (an `OAuthProxy` DCR-face bundled with Google's token
verifier). FastMCP **mints and verifies its own HS256 bearer token** bound to the user; claude.ai
never sees a Google token. We write **no JWT code**.

```python
# auth/provider.py — ⚠ verify kwarg names against fastmcp 3.4.2 at build
from fastmcp.server.auth.providers.google import GoogleProvider
provider = GoogleProvider(
    client_id=cfg.google_oauth_client_id,
    client_secret=cfg.google_oauth_client_secret.get_secret_value(),
    base_url=cfg.public_server_url,              # RFC 9728 resource must == deployed URL
    required_scopes=["openid", "email", "profile"],   # identity only, NO Drive
    jwt_signing_key=cfg.jwt_signing_key.get_secret_value(),  # FIXED, not per-boot
    client_storage=make_store(cfg),              # §5 — persistence
)
```

**Org gate — two layers (see PRD A2):**
1. **Primary (Google-side):** the Google OAuth app is set to **Internal (Workspace-only)**. A
   non-Aretea identity never receives an auth code → **no token minted**. This is what satisfies
   AC3 "no token issued"; it is *not* enforceable in our code.
2. **Defense-in-depth (our code, post-mint):** an authorization check refuses any session whose
   `email` claim doesn't end in `@aretea-group.com`. This enforces "no data reachable," not "no
   token." `hd`/`email_verified` are **not** in GoogleProvider's default claims — do not rely on them.

**Identity in a request:** `from fastmcp.server.dependencies import get_access_token` →
`.claims["email"]` / `.claims["sub"]`. Used by the domain check and the audit middleware (§4).

**Attribution is transport-dependent.** FastMCP binds a distinct token *per identity* only if
claude.ai runs a per-user client-hop flow — the load-bearing spike unknown (PRD §2.2). FastMCP
cannot manufacture attribution the transport doesn't carry.

**⚠ Double-consent:** `require_authorization_consent` defaults `True` → FastMCP shows its own consent
screen atop Google's. FR2′ budgets exactly one prompt; decide the value in the spike (PRD A4).

---

## 3. Drive hop — service-account contract

```python
# google/credentials.py
from google.oauth2 import service_account
READ_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/presentations.readonly",
]
creds = service_account.Credentials.from_service_account_info(
    json.loads(cfg.google_sa_key_json.get_secret_value()), scopes=READ_SCOPES,
)
# INVARIANT (AC9): never call creds.with_subject(...) — that is the DWD/impersonation switch.
assert getattr(creds, "_subject", None) is None
```

- **Clients:** Drive v3, Sheets v4, Slides v1, built with `static_discovery=True` (offline `build()`).
- **Every query pinned:** `corpora="drive"`, `driveId=AI_VISIBLE_DRIVE_ID`,
  `includeItemsFromAllDrives=True`, `supportsAllDrives=True`.
- **Second wall (AC10):** before returning any file's content, assert `file.driveId ==
  AI_VISIBLE_DRIVE_ID`. Membership is the boundary; this is defense-in-depth against a scoping bug.

**Sync→async bridge (the real concurrency decision).** `google-api-python-client` is **blocking**
and `httplib2.Http` is **not thread-safe**. Tools are `async def`; each offloads the blocking
`.execute()` and uses a **fresh** authorized http per call:

```python
import anyio, httplib2
from google_auth_httplib2 import AuthorizedHttp
def _run(request):                       # request built with a per-call AuthorizedHttp
    return request.execute(num_retries=5)   # num_retries covers 429/5xx; default is 0 — must set
result = await anyio.to_thread.run_sync(_run)
```

Do **not** share one module-level service across threads. Credentials object *is* shareable.

---

## 4. Tools — I/O contract (read-only, FR6)

Only read tools exist in the schema. No create/update/delete/share/permission tool is defined (AC8).

| Tool | Google call | Returns |
|---|---|---|
| `drive_search(query, page_size=25, page_token=None)` | `files.list` (scoped) | `{files:[{id,name,mimeType,modifiedTime,owners,webViewLink,size}], next_page_token}` |
| `drive_get_metadata(file_id)` | `files.get` (+driveId assert) | one file dict (fields above) |
| `drive_read_file(file_id, sheet=None, range=None, page_token=None)` | dispatch by mimeType ↓ | `{mime_type, content, truncated: bool, next_page_token?}` |

`drive_read_file` dispatch:
- **Google Doc** → `files.export(mimeType="text/plain")` (⚠ `text/markdown` is a cheap fidelity
  upgrade — headings/lists preserved; decide in build).
- **Google Sheet** → `spreadsheets.get` (tab names) → `spreadsheets.values.batchGet`
  (`valueRenderOption="UNFORMATTED_VALUE"`). **Values only, no formulas.** `sheet`/`range` page.
- **Google Slides** → `presentations.get` → per-slide shape text. **Text only, no layout.**
- **Regular/non-native** → plain-text mimetypes via `files.get(alt="media")`; binaries (PDF/Office)
  → metadata + `"binary — not text-extracted in v1"`. PDF/Office extraction is a fast-follow.

**Size guardrail (AC11):** every read caps output at a configurable char/row limit and sets
`truncated=True` with an explicit note. **Never silently cut.** `sheet`/`range`/`page_token` page.

**Audit middleware** wraps every tool call:

```python
# audit.py — one JSON line per call to stdout (Railway captures it)
class AuditMiddleware(Middleware):
    async def on_call_tool(self, ctx, call_next):
        tok = get_access_token()
        ... time it, run call_next(ctx), emit:
        # {"ts","user":<email>,"tool","args_summary","outcome":"ok|error","duration_ms"}
```

No file *contents* are ever logged.

---

## 5. State / storage contract

**FastMCP-native persistence** (PRD A1 — there is **no SQLite backend**). `client_storage` is an
`AsyncKeyValue`; FastMCP auto-persists OAuth tokens + DCR client registrations through it.

```python
# auth/store.py
from cryptography.fernet import Fernet
from key_value.aio.stores.filetree import FileTreeStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
def make_store(cfg):
    disk = FileTreeStore(data_directory=cfg.storage_dir)         # on the Railway volume
    return FernetEncryptionWrapper(disk, fernet=Fernet(cfg.storage_encryption_key.get_secret_value()))
```

- **Two fixed secrets, both required:** `JWT_SIGNING_KEY` (token signing) **and**
  `STORAGE_ENCRYPTION_KEY` (Fernet, at-rest). On Linux the default salt is **ephemeral** — without a
  fixed encryption key, ciphertext survives restart but the key doesn't → tokens are lost. Both must
  be fixed env secrets, not per-boot.
- **No bespoke token DB.** Per-user **revoke = a Google-side action** (disable/remove the Workspace
  identity), consistent with the Internal-app gate (PRD A3).
- Single-instance (SQLite-free but same constraint): one replica; volume follows the service region.
  Redis is the scale path, not v1.

---

## 6. Code layout & seams (NFR6)

`gdrive/` (not `google/`) avoids shadowing the real `google` namespace package.

```
aretea_drive_mcp/
  main.py            # ASGI entrypoint: app = mcp.http_app(path="/mcp"); mount w/ lifespan=app.lifespan  ⚠
  server.py          # build FastMCP(name, auth=provider, middleware=[AuditMiddleware()]); register toolsets
  config.py          # pydantic-settings BaseSettings; SecretStr; fail-fast at boot
  init_db.py         # idempotent storage-dir init — run in start command, NOT build (volume absent at build)
  audit.py           # per-user JSON on_call_tool middleware
  auth/
    provider.py      # GoogleProvider config + @aretea-group.com domain check
    store.py         # FileTreeStore + Fernet  (make_store)
  gdrive/
    credentials.py   # SA loader; asserts no DWD; 3 read scopes
    client.py        # scoped Drive/Sheets/Slides builders + driveId assertion + async bridge
  toolsets/
    base.py          # register(app) -> None   ← Slack/HubSpot/Granola drop in behind identical auth
    drive.py         # the read tools + dispatch + size guardrail
tests/               # unit tests of OUR invariants (AC8,9,10,11 + domain gate); AC1-7,12 = real-API integration (spike/CI)
Dockerfile · railway.json · .env.example
```

**Toolset seam:** `toolsets/base.py` defines `register(app: FastMCP) -> None`; a future connector is
one new module calling `app.tool(...)`, behind the identical auth front. Auth + hosting solved once.

---

## 7. Config & secrets (`config.py`, all `SecretStr` where sensitive)

| Var | Purpose |
|---|---|
| `GOOGLE_SA_KEY_JSON` | service-account key (drive hop) |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | upstream OIDC (identity); held server-side, **never** pasted into claude.ai |
| `JWT_SIGNING_KEY` | fixed — FastMCP mints/verifies our bearer token |
| `STORAGE_ENCRYPTION_KEY` | fixed Fernet key — at-rest token storage (**new, A1**) |
| `AI_VISIBLE_DRIVE_ID` | the one allowed shared drive |
| `PUBLIC_SERVER_URL` | must equal the deployed HTTPS URL (RFC 9728 `resource`) |
| `ALLOWED_EMAIL_DOMAIN` | `aretea-group.com` (post-mint domain check) |
| `STORAGE_DIR` | path on the Railway volume |

Names only in `.env.example` — no values committed (NFR7).

---

## 8. Request path & failure behavior

1. `MCP request` → FastMCP validates our bearer token. Invalid/expired → **401**.
2. Domain check: `email` not `@aretea-group.com` → **403, no tool runs** (defense-in-depth).
3. Audit middleware starts timing, binds identity.
4. Tool executes via the service account (offloaded to a thread):
   - Google `429`/`5xx` → `num_retries=5` exponential backoff; still failing → tool returns an error
     result (logged `outcome:"error"`), not a crash.
   - `file.driveId != AI_VISIBLE_DRIVE_ID` → **refuse before returning content** (AC10).
   - Output over cap → `truncated=True` + explicit note (AC11).
5. Audit middleware emits exactly one JSON line (AC12).

---

## 9. Deployment (Railway EU-West)

- **Dockerfile:** uv multi-stage (`ghcr.io/astral-sh/uv:python3.13-*`, `UV_COMPILE_BYTECODE=1`,
  `uv sync --frozen --no-dev`), copy `.venv`, run uvicorn (single worker — in-memory sessions +
  single volume).
- **railway.json:** `builder: DOCKERFILE`; region pinned via `multiRegionConfig`
  (`europe-west4-drams3a` = EU-West Amsterdam Metal), `numReplicas: 1`.
- **Start command initializes storage at runtime, not build** (volume mounts as root at runtime):
  `sh -c 'python -m aretea_drive_mcp.init_db && uvicorn aretea_drive_mcp.main:app --host 0.0.0.0 --port $PORT'`.
  ⚠ Do **not** wrap `http_app()` in a parent app to add an init-lifespan — it can shadow FastMCP's
  session-manager lifespan and the server silently won't serve. Use the separate init process above.
- Volumes mount as **root**: either chown-at-start then drop privileges, or run root (acceptable for
  a single-tenant internal container — the real boundaries are SA membership + the identity gate).

---

## 10. CI/CD & release pipeline (`prd_02`)

The connector ships through a gated, token-free pipeline: **PR → green CI → merge → Railway
autodeploy → `/health` probe → live → `vX.Y.Z` tag + GitHub Release**. Two decoupled halves — CI
runs in GitHub Actions; CD is Railway-native. They meet at **Wait for CI**.

### 10.1 Health signal (`health.py` → `/health`)

`register_health(app)` adds a FastMCP **`custom_route`** (`server.py` wires it after the toolset):

```python
@app.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health(_request): return JSONResponse(health_payload())
# {"status":"ok", "commit":$RAILWAY_GIT_COMMIT_SHA, "version":<floor>, "region":$RAILWAY_REPLICA_REGION}
```

- **Unauthenticated by construction (spike, resolved).** FastMCP wraps `RequireAuthMiddleware`
  around **only** the `/mcp` route; custom routes are added to `server_routes` unwrapped. The global
  `AuthenticationMiddleware` runs on every route but its `BearerAuthBackend.authenticate` **returns
  `None`** on a missing/invalid token (never raises), so `/health` proceeds anonymously → 200. And
  `AuditMiddleware` is a **tool-call** middleware (`on_call_tool`) — a plain GET is not a tool call,
  so the org gate is never consulted. Proven in `tests/test_health.py` (auth stack present:
  `/health`→200, `/mcp`→401). ⚠ Re-verify against the pinned fastmcp if the auth wiring changes.
- **Reports "up," not "Drive works."** It never calls Google (would be flaky/rate-limited). Health
  layering: fail-fast config at boot → `/health` (process up + config loaded) → **manual** claude.ai
  web Drive-read smoke test. Different failure classes, each caught once.
- **No parent wrapper app.** A Starlette/FastAPI wrapper is forbidden (shadows `http_app`'s
  session-manager lifespan — §9). `custom_route` is the only sanctioned way to add `/health`.
- Wired as `healthcheckPath: "/health"` in `railway.json`; a deployment that never returns 200 is
  not routed traffic and is marked failed (AC4).

### 10.2 Version identity

`RAILWAY_GIT_COMMIT_SHA` (injected by native connect at build + runtime) is the source of truth,
surfaced at `/health.commit`. The literal `vX.Y.Z` string is **not** in-container (`.dockerignore`
drops `.git`, and Railway exposes no tag build-var), so the tag/Release is the **human label mapped
from the SHA on GitHub**. `pyproject` `project.version` is a **floor** read via
`importlib.metadata` (`__init__.py`) — never hand-duplicated, never bumped by the release job.

### 10.3 CI (`.github/workflows/ci.yml`)

One workflow, `on: push:[main]` **and** `on: pull_request`. Secret-free (uses the auto `GITHUB_TOKEN`).

| Job | Does | Gate role |
|---|---|---|
| `check` | `ruff check` · `ruff format --check` · `mypy --strict` · `pytest` | required to merge (AC1) |
| `docker` | `docker build` (no push) — catch Dockerfile breakage before Railway | required to merge |
| `release` | `needs:[check,docker]`, **main-push only** — cut the tag + Release | see §10.5 |

`concurrency` supersedes in-flight **PR** runs but never cancels a main run (a half-cut tag is worse
than a redundant run). A red `check`/`docker` fails the workflow → Wait for CI leaves the deploy
`SKIPPED` (AC5) and the `release` job never runs.

### 10.4 CD — Railway native connect + Wait for CI

No deploy step runs in Actions and **no `RAILWAY_TOKEN` lives in GitHub** (one fewer long-lived prod
credential). Railway's GitHub App watches `main`; with **Wait for CI** on, the deploy holds in
`WAITING` until this workflow succeeds, then builds the Dockerfile and probes `/health`. Brief
downtime per deploy: the single attached volume forbids two concurrent deployments, so in-memory MCP
sessions drop on every deploy (accepted for an internal connector — see PRD Non-Goals).

### 10.5 Release automation — tag-only, **no write-back** (load-bearing)

`python-semantic-release` (`[tool.semantic_release]` in `pyproject.toml`) derives the next SemVer
from Conventional Commits and creates the **`vX.Y.Z` tag + GitHub Release only**. The action runs
with `commit: false` (and `version_toml`/`version_variables` unset, so nothing is stamped):

> **Invariant:** the release must never push a write-back commit to `main`. A bump commit would
> (a) fire a *second* Railway autodeploy — a double deploy (AC9) — and (b) be rejected outright once
> branch protection is on. Current version is read from the latest `vX.Y.Z` git **tag**, not source.

Config: `allow_zero_version=true`, `major_on_zero=false` (stay on 0.x; `feat:`→minor, `fix:`→patch;
`docs:`/`chore:` do not release). First automated release from a tagless history is `v0.1.0`
(matches the floor); thereafter a `feat:` merge cuts `v0.2.0`, etc. `/health.commit` for a live
deploy equals the commit of its Release (AC8) — "what's live == what was released."

### 10.6 Rollback runbook (manual, no rebuild)

Railway retains prior deployments; rollback re-points traffic at a known-good one without rebuilding.

1. **Confirm the bad state:** `curl -s https://<PUBLIC_SERVER_URL>/health` — note the live `commit`.
2. **Railway → the service → Deployments:** find the last-good deployment (its commit maps to a
   `vX.Y.Z` Release on GitHub). Use its **⋯ → Redeploy** (a.k.a. "Rollback to this deployment").
3. **Verify:** re-`curl` `/health` and confirm `commit` now equals the **prior** SHA (AC7). Confirm a
   claude.ai web Drive read works (the manual smoke test).
4. **Caveats to record every time:**
   - Rolling back **code does not revert env-var / secret changes** — if the incident involved a var
     edit, revert that separately in Railway.
   - A change to the **on-disk storage format** (FastMCP token store on the volume) can break
     rollback. Any format change needs a migration + compatibility note, and `init_db` must stay
     idempotent and forward/backward-compatible.

### 10.7 One-time operator setup (Railway / GitHub UI — not in this repo)

These are console actions the repo cannot perform; do them once to activate the pipeline:

- **Railway GitHub App:** grant repo access + accept permissions; connect the service source to the
  repo; set trigger branch `main`; enable **Wait for CI**. Confirm the service builder flips
  `RAILPACK → DOCKERFILE` (the committed `railway.json` takes effect).
- **Branch protection on `main`:** require the `check` and `docker` status checks; require PRs.
- **Env/secret parity:** ensure Railway has every var from `.env.example` (`PORT=8080`,
  `PUBLIC_SERVER_URL` = exact deployed HTTPS URL, `STORAGE_DIR=/data/storage`, the fixed
  `JWT_SIGNING_KEY` / `STORAGE_ENCRYPTION_KEY`) and a persistent volume at `/data`.
- **Release job:** needs no secret beyond the auto `GITHUB_TOKEN` (used with `contents: write`).
