# Aretea Drive MCP connector (read-only, v1)

Self-hosted MCP server that gives Claude web read access to **one** curated Google Drive corpus.
Two decoupled hops: an **identity-only** client hop (no Drive scopes granted to users) and a fixed
**service-account** data hop whose Shared-Drive membership is the security boundary.

- Product spec: [`prds/prd_01_aretea_drive_mcp_connector_read_only_v1.md`](prds/prd_01_aretea_drive_mcp_connector_read_only_v1.md)
- Architecture / contracts: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Status — honest

The code is written and the wiring compiles against real FastMCP 3.4.2 — but *compiles* is not
*works*. **Testing policy: test against the real API or don't write the test** (see
`docs/ARCHITECTURE.md` → Testing principle); we don't mock Google/OAuth to fake a green AC.

- ✅ **Unit-tested — our own invariants only** (no external calls to fake): AC8 read-only schema,
  AC9 no-delegation + 3 read scopes, AC10 driveId boundary wall, AC11 explicit truncation, AC3
  code-side domain gate. `uv run pytest` → 20 passing; `ruff` + `mypy --strict` clean.
- ⛔ **Not yet covered — needs real services** (built in the spike/CI, not mocked): the client-hop
  OAuth flow on claude.ai web (AC1–AC4) against a test Workspace client, Drive/Sheets/Slides reads
  (AC5–AC7) against a dedicated test Shared Drive, and per-user audit lines (AC12). These ACs stay
  visibly un-covered until tested live. Google API method/field names are marked `⚠ verify at build`.

## Layout

```
aretea_drive_mcp/  auth/ (GoogleProvider + FileTreeStore/Fernet), gdrive/ (SA creds + scoped client),
                   toolsets/ (read tools + seam), audit.py, config.py, server.py, main.py, init_db.py
tests/             unit ACs (8, 9, 10, 11) + domain gate
```

## Develop

```bash
uv sync --extra dev
uv run ruff check .
uv run mypy aretea_drive_mcp
uv run pytest -q
```

## Run locally

Populate `.env` from `.env.example` (all vars required), then:

```bash
uv run python -m aretea_drive_mcp.init_db
uv run uvicorn aretea_drive_mcp.main:app --host 0.0.0.0 --port 8000
```

## Deploy (Railway EU-West)

`Dockerfile` + `railway.json` pin the build to EU-West Amsterdam (`europe-west4-drams3a`), single
replica (in-memory sessions + one volume). Attach a persistent volume mounted at `STORAGE_DIR`, set
all secrets as Railway variables, and confirm `PUBLIC_SERVER_URL` equals the deployed HTTPS URL.
