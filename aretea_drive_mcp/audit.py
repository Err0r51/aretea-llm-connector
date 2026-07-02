"""Per-user audit + the post-mint org domain gate, as one middleware.

Every tool call emits exactly one structured-JSON line to stdout (Railway captures it) — AC12:
``{ts, user, tool, args_summary, outcome, duration_ms}``. No file *contents* are ever logged.

The middleware also enforces the post-mint domain gate (PRD A2 defense-in-depth): a session whose
email is outside the allowed domain is refused before the tool runs, and the refusal is logged as
``outcome="denied"``. This is "no data reachable," not "no token issued" — the latter is the
Google-side Internal-app restriction, not code.

⚠ ``get_access_token`` / ``MiddlewareContext`` field access is the documented FastMCP 3.x API;
verify names against fastmcp 3.4.2 at build. The canonical home for the domain check may be a
FastMCP authorization hook; enforcing it here guarantees it runs regardless.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware, MiddlewareContext

from aretea_drive_mcp.auth.provider import email_in_domain

log = structlog.get_logger("audit")


def configure_logging() -> None:
    """Emit all logs as single-line JSON to stdout."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="ts"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _current_user() -> str | None:
    """Best-effort authenticated identity (email, else subject) for attribution."""
    try:
        token = get_access_token()
    except Exception:
        return None
    if token is None:
        return None
    claims: dict[str, Any] = getattr(token, "claims", {}) or {}
    return claims.get("email") or claims.get("sub")


def _summarize_args(arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Log identifiers/short scalars only — never file contents."""
    if not arguments:
        return {}
    summary: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, str):
            summary[key] = value if len(value) <= 120 else f"<str:{len(value)}chars>"
        elif isinstance(value, (int, float, bool)) or value is None:
            summary[key] = value
        else:
            summary[key] = f"<{type(value).__name__}>"
    return summary


class AuditMiddleware(Middleware):
    """Enforce the domain gate and emit one audit line per tool call."""

    def __init__(self, allowed_domain: str) -> None:
        self._allowed_domain = allowed_domain

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:
        message = getattr(context, "message", None)
        tool = getattr(message, "name", "<unknown>")
        args_summary = _summarize_args(getattr(message, "arguments", None))
        user = _current_user()

        # Post-mint org gate (defense-in-depth): outside-domain → refuse, still logged.
        if not email_in_domain(user, self._allowed_domain):
            log.info(
                "tool_call",
                user=user,
                tool=tool,
                args_summary=args_summary,
                outcome="denied",
                duration_ms=0,
            )
            raise ToolError("caller identity is not in the allowed domain")

        start = time.monotonic()
        outcome = "ok"
        try:
            return await call_next(context)
        except Exception:
            outcome = "error"
            raise
        finally:
            log.info(
                "tool_call",
                user=user,
                tool=tool,
                args_summary=args_summary,
                outcome=outcome,
                duration_ms=round((time.monotonic() - start) * 1000, 1),
            )
