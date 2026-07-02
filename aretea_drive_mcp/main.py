"""ASGI entrypoint. Run with: ``uvicorn aretea_drive_mcp.main:app``.

We expose FastMCP's own ``http_app`` **directly** (no parent Starlette/FastAPI wrapper) so its
lifespan — which starts the Streamable-HTTP session manager — is not shadowed (ARCHITECTURE §9,
python-sdk #1367). Storage-dir init happens in a separate start-command step, not a wrapping
lifespan.
"""

from __future__ import annotations

from aretea_drive_mcp.server import build_app

mcp = build_app()

# Streamable HTTP ASGI app; endpoint served at /mcp. lifespan is carried by this app object.
app = mcp.http_app(path="/mcp")
