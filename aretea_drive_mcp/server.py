"""Assemble the FastMCP app: auth front, audit/gate middleware, and the Drive toolset.

⚠ The ``FastMCP(...)`` constructor kwargs (``auth=``, ``middleware=``) are the documented v3 API;
FastMCP 3.0 moved some config to ``run()``/``run_http_async()``. Re-validate the exact wiring
against fastmcp 3.4.2 at build. The whole client hop is spike-gated (PRD Phase 1).
"""

from __future__ import annotations

from fastmcp import FastMCP

from aretea_drive_mcp.audit import AuditMiddleware, configure_logging
from aretea_drive_mcp.auth.provider import build_provider
from aretea_drive_mcp.config import Settings, get_settings
from aretea_drive_mcp.gdrive.client import DriveClient
from aretea_drive_mcp.toolsets import drive


def build_app(settings: Settings | None = None) -> FastMCP:
    """Build the fully wired connector app."""
    settings = settings or get_settings()
    configure_logging()

    app = FastMCP(
        name="aretea-drive",
        auth=build_provider(settings),
        middleware=[AuditMiddleware(settings.allowed_email_domain)],
    )

    client = DriveClient(
        sa_key_json=settings.google_sa_key_json.get_secret_value(),
        drive_id=settings.ai_visible_drive_id,
        num_retries=settings.drive_num_retries,
    )
    drive.register(app, client=client, max_read_chars=settings.max_read_chars)
    return app
