# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Self-hosted MCP server (Python + FastMCP) giving Claude **web** read-only access to **one** curated
Google Drive corpus. It is the first of several planned connectors (Slack/HubSpot/Granola next), so
the auth + hosting pattern here is meant to be reused. The *what/why* live in
`prds/prd_01_aretea_drive_mcp_connector_read_only_v1.md`; the *how* in `docs/ARCHITECTURE.md`. Read
the PRD before implementing feature work.

## Commands

```bash
uv sync --extra dev                                  # install incl. dev tools (mypy/pytest/ruff live under the `dev` extra)
uv run ruff check .                                  # lint
uv run ruff format .                                 # format
uv run mypy aretea_drive_mcp                         # types (strict)
uv run --extra dev pytest -q                         # full suite (39 cases)
uv run --extra dev pytest tests/test_gate_identity.py::test_no_email_claim_raises_distinct_error_and_does_not_run_tool -q   # one test
uv run --extra dev pytest -k "export_size or search_drop" -q          # by keyword
```

Run locally (fill `.env` from `.env.example` first — every var is required and validated at boot):

```bash
uv run python -m aretea_drive_mcp.init_db            # create the storage dir
uv run uvicorn aretea_drive_mcp.main:app --host 0.0.0.0 --port 8000
```

Deploy: `railway up` (linked to Railway project `aretea-llm-connector`, EU `europe-west4`). An
unauthenticated `GET /mcp` on a healthy deploy returns **401** with a `WWW-Authenticate: Bearer`
challenge — that is the correct response, not an error.

## Architecture — the big picture

**Two decoupled auth hops (this is the whole design).** They never mix:

- **Client hop = identity only.** `auth/provider.py` builds a FastMCP `GoogleProvider` (an
  `OAuthProxy` fronting Google Workspace OIDC) requesting scopes `openid email profile` — **users are
  granted zero Drive scopes** (FR2′). FastMCP mints/verifies its own bearer token; we write no JWT.
- **Data hop = fixed service account.** `gdrive/credentials.py` loads read-only SA credentials with
  **no** `with_subject`/domain-wide delegation (`assert_no_delegation`). The security boundary is the
  SA's *membership of the single AI-Visible Shared Drive* — not application logic.

**The Drive boundary is enforced twice** (`gdrive/client.py`): every query is pinned to the one
drive (`corpora="drive"`, `driveId=…`), and every file's `driveId` is re-checked before content is
returned. Note the asymmetry: single-file `get_metadata`/`read_file` **raise** `DriveBoundaryError`
(refuse); the `search` list endpoint **drops** stray rows and logs a warning (one bad row must not
sink the whole result set).

**The org-domain gate is post-mint defense-in-depth** (`audit.py` `AuditMiddleware`). It reads the
`email` claim from `get_access_token().claims` (populated per-request by FastMCP's
`GoogleTokenVerifier`) and refuses callers outside the allowed domain. The gate decision uses the
`email` claim **only** — never the `sub` fallback (a numeric sub would fail the suffix match and
mislead); `email or sub` is used only for the audit line. Missing-email is a distinct
`denied_no_email` refusal, not a domain mismatch. The same middleware emits exactly one JSON audit
line per tool call (AC12).

**Extensibility seam** (`toolsets/`): a connector is a module exposing `register(app, **deps)` (see
`toolsets/base.py`). Connector #2 is a new module behind the *identical* auth front — auth and
hosting are solved once. Adding a mutation tool is out of scope by construction: no
create/update/delete tool exists anywhere in the schema (AC8 holds structurally).

**Blocking-client concurrency** (`gdrive/client.py`): `google-api-python-client` is blocking and
`httplib2.Http` is not thread-safe. Public methods are `async` and offload to
`anyio.to_thread.run_sync`; each threaded call builds its **own** service on a fresh authorized http
(credentials are shared, which is safe). Don't call the Google client on the event loop.

**Boot & storage.** `config.py` loads all settings from the environment via pydantic-settings,
fail-fast, secrets as `SecretStr`. `main.py` exposes FastMCP's `http_app` **directly** (no wrapping
Starlette app) so its lifespan/session-manager isn't shadowed. Token storage is a FastMCP-native
`FileTreeStore` + `FernetEncryptionWrapper` on the Railway volume; the Fernet key **must be fixed**
across restarts or tokens are unreadable (amendment A1). `init_db.py` creates the storage dir at
container start because the volume is absent at build time.

## Conventions & invariants

- **Test against the real API or don't write the test.** Never mock Google/OAuth to fake a green
  acceptance criterion. Unit tests cover **our own invariants only** (pure functions, or
  `DriveClient.__new__` + monkeypatched `anyio.to_thread.run_sync` / `get_access_token`). Every code
  change ships with its tests — that's the Definition of Done.
- **Security checks are explicit `raise`s, not `assert`** (`DelegationError`, `DriveBoundaryError`) —
  `assert` is compiled out under `python -O`. `S101` is ignored in ruff for this reason.
- **Spike-gated / verify-at-build.** The FastMCP 3.4.2 wiring compiles but the claude.ai **web**
  OAuth handshake and the Drive/Sheets/Slides reads are only validated live (PRD Phase 1 spike /
  Phase 4 web smoke test). Comments marked `⚠ verify at build` flag Google API method/field names
  and FastMCP kwargs that need checking against the pinned libs — respect them.
- **PRDs live in `prds/`** (`prd_NN_…`, each with acceptance criteria mapped to tests); other docs
  live in `docs/`, incl. `ARCHITECTURE.md` (the ~1-page capability index — consult before adding
  cross-cutting infra like a new auth flow or storage layer). **Never delete a PRD** — keep every
  `prd*` file in `prds/`; move or archive, never `git rm`, even a superseded draft.

## Railway deploy specifics (each cost a failed deploy to learn)

Encoded in `Dockerfile` / `railway.json`; don't "simplify" them back:

- **`COPY`, not `RUN --mount`** — Railway's Metal builder rejects *all* `RUN --mount` types (cache
  and bind).
- **Start command is `/bin/sh -c "…"`** in `railway.json` — Railway runs a Dockerfile start command
  in *exec form* (no `&&` chaining, no `$PORT` expansion), so an unwrapped `init_db && uvicorn` runs
  only `init_db`.
- **uvicorn binds `0.0.0.0`** — the Railway edge connects over IPv4; a `::`-only bind is refused (502).
- **`.dockerignore` re-includes `README.md`** (`!README.md`) — hatchling reads it while building the
  wheel; excluding it fails the build.
- Set `PORT=8080` (matches the generated domain's target port), `PUBLIC_SERVER_URL` = the exact
  deployed HTTPS URL, and attach a persistent volume at `/data` (`STORAGE_DIR=/data/storage`).
