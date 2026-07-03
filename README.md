# Aretea Drive MCP connector (read-only, v1)

Self-hosted MCP server that gives Claude web read access to **one** curated Google Drive corpus.
Two decoupled hops: an **identity-only** client hop (users are granted no Drive scopes) and a fixed
**service-account** data hop whose Shared-Drive membership is the security boundary.

- Product spec: [`docs/prd_01_aretea_drive_mcp_connector_read_only_v1.md`](docs/prd_01_aretea_drive_mcp_connector_read_only_v1.md)
- Architecture / contracts: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Status

Deployed to **Railway EU** (`europe-west4`). The OAuth-protected MCP endpoint is live and returns a
correct **401 bearer challenge** (with RFC 9728 `resource_metadata`) to unauthenticated callers —
the auth front is wired and responding.

**Not yet validated end-to-end** (per the PRD phasing): the claude.ai **web** OAuth handshake and
the Drive/Sheets/Slides reads. Those need the Phase-1 spike and the post-deploy web smoke test — a
live 401 proves the server is up, not that a real Claude-web connection completes.

Testing policy: **test against the real API or don't write the test** (see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) → Testing principle). We don't mock Google/OAuth to
fake a green acceptance criterion; the unit tests cover only our own invariants.

Live endpoint: `https://trustworthy-expression-production-26d9.up.railway.app/mcp`

## Layout

```
aretea_drive_mcp/
  auth/       GoogleProvider (identity-only) + encrypted FileTreeStore token store
  gdrive/     service-account creds (no delegation) + scoped, boundary-checked Drive client
  toolsets/   read tools (search / get-metadata / read-file) behind a register() seam
  audit.py    one JSON audit line per call + post-mint org-domain gate
  config.py   env-loaded settings, validated once at boot (fail-fast)
  server.py   assembles auth + audit middleware + the Drive toolset
  main.py     ASGI entrypoint (uvicorn serves FastMCP's http_app at /mcp)
  init_db.py  creates the volume storage dir at container start
tests/        invariant-only unit tests: read-only schema (AC8), no-delegation + scopes (AC9),
              driveId boundary (AC10), explicit truncation (AC11), domain gate (AC3), gate
              identity + fail-loud, provider scope guard, Doc export-size, search drop
```

## Develop

```bash
uv sync --extra dev
uv run ruff check .
uv run mypy aretea_drive_mcp
uv run pytest -q          # 32 passing
```

## Run locally

Populate `.env` from `.env.example` (all vars required), then:

```bash
uv run python -m aretea_drive_mcp.init_db
uv run uvicorn aretea_drive_mcp.main:app --host 0.0.0.0 --port 8000
```

## Deploy (Railway, EU-West)

`Dockerfile` + `railway.json` build the image and pin it to EU-West Amsterdam
(`europe-west4-drams3a`), single replica (in-memory sessions + one volume).

1. Attach a **persistent volume** mounted at `/data` (`STORAGE_DIR=/data/storage`) so OAuth tokens
   survive restarts.
2. Set every `.env.example` key as a **Railway variable** (secrets included). Set `PORT=8080` to
   match the generated domain's target port, and `PUBLIC_SERVER_URL` to the exact deployed HTTPS URL.
3. `railway up` — builds the Dockerfile and deploys.

Railway-builder specifics baked into the config (each cost a failed deploy to discover):

- **`COPY`, not `RUN --mount`.** Railway's Metal builder rejects all `RUN --mount` types (cache
  *and* bind), so the `uv sync` layers copy the lockfiles instead of bind-mounting them.
- **Start command is shell-wrapped.** Railway runs a Dockerfile start command in *exec form* (no
  variable expansion, no `&&` chaining), so `railway.json` wraps it in `/bin/sh -c "…"` — otherwise
  `init_db && uvicorn` runs only `init_db` and `$PORT` never expands.
- **Bind `0.0.0.0`.** The Railway edge reaches the container over IPv4; a `::`-only bind is refused.
- **Keep `README.md` in the build context.** `.dockerignore` excludes `*.md` but re-includes
  `README.md` (`!README.md`) because hatchling reads it while building the wheel.
