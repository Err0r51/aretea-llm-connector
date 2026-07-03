"""Unauthenticated ``GET /health`` — deploy-time liveness for Railway's healthcheck (PRD 3).

**What it reports.** Process is up + config loaded, NOT "Drive works": it never calls the Google
API (that would make the probe flaky and rate-limited). Health layering is deliberate — fail-fast
config at boot (bad secrets → container never starts) → this route (process up, config loaded) →
a *manual* post-deploy Drive-read smoke test on claude.ai web. Each catches a different failure
class.

**Why it is reachable without a bearer token / without tripping the org gate.** It registers as a
FastMCP ``custom_route``, which lands in ``server_routes`` with **no** ``RequireAuthMiddleware``
wrapper — that wrapper is applied by FastMCP only to the ``/mcp`` route, not to custom routes
(``fastmcp.server.http.create_streamable_http_app``). The global ``AuthenticationMiddleware``
*does* run on every route, but its ``BearerAuthBackend.authenticate`` **returns ``None``** on a
missing/invalid token (it never raises), so the request proceeds anonymously → 200. And
``AuditMiddleware`` is a tool-call middleware (``on_call_tool``); a plain HTTP GET is not a tool
call, so the domain gate is never consulted. Verified at build against fastmcp 3.4.2.

Wired as ``healthcheckPath`` in ``railway.json``. Railway probes over the
``healthcheck.railway.app`` host; Starlette routes do not filter by Host (no
``TrustedHostMiddleware`` is installed), so any Host header is accepted.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import JSONResponse

from aretea_drive_mcp import __version__

if TYPE_CHECKING:
    from fastmcp import FastMCP

# Injected by Railway's native GitHub connect at build + runtime (guaranteed). Absent when running
# locally / in tests → "unknown", which is honest rather than a misleading fake SHA.
_COMMIT_ENV = "RAILWAY_GIT_COMMIT_SHA"
_REGION_ENV = "RAILWAY_REPLICA_REGION"


def _env_or_unknown(name: str) -> str:
    """Return the env var's value, or ``"unknown"`` when it is absent **or blank**.

    ``os.environ.get(name, "unknown")`` guards only the *absent* case; Railway can inject the var
    as an empty string (e.g. a non-git-sourced deploy), which would surface a misleading blank
    ``commit``/``region`` instead of the honest ``"unknown"`` the docstring promises.
    """
    return os.environ.get(name, "").strip() or "unknown"


def health_payload() -> dict[str, str]:
    """The ``/health`` body. Pure + import-safe so it is unit-testable without an ASGI server.

    ``commit`` is the deployed commit SHA — it maps 1:1 to the ``vX.Y.Z`` GitHub Release cut for
    that commit, so "what's live == what was released" is answerable at any time (PRD 3
    traceability).
    """
    return {
        "status": "ok",
        "commit": _env_or_unknown(_COMMIT_ENV),
        "version": __version__,
        "region": _env_or_unknown(_REGION_ENV),
    }


def register_health(app: FastMCP) -> None:
    """Register the unauthenticated ``GET /health`` route on the FastMCP app."""

    @app.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_request: Request) -> JSONResponse:
        # no-store: the payload names the *currently live* commit SHA; a cached edge response
        # would misreport "what's live == what was released" (the PRD 3 traceability contract).
        return JSONResponse(health_payload(), headers={"Cache-Control": "no-store"})
