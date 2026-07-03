"""Per-user audit + the post-mint org domain gate, as one middleware.

Every tool call emits exactly one structured-JSON line to stdout (Railway captures it) — AC12:
``{ts, user, tool, args_summary, outcome, duration_ms}``. No file *contents* are ever logged.

The middleware also enforces the post-mint domain gate (PRD A2 defense-in-depth) before the tool
runs, with two distinct, logged refusals: an outside-domain email → ``outcome="denied"``, and a
token carrying no email claim at all → ``outcome="denied_no_email"`` (an auth/scope problem, kept
separate so it can't hide as a domain mismatch). This is "no data reachable," not "no token
issued" — the latter is the Google-side Internal-app restriction, not code.

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


def _get_claims() -> dict[str, Any]:
    """Claims of the current authenticated token, or ``{}`` if there is none.

    ``get_access_token`` failing is an auth-layer problem, not a per-user one — log it loudly
    rather than swallowing it into a silent no-identity (which would look like a domain denial).
    """
    try:
        token = get_access_token()
    except Exception:
        log.warning("auth.token_fetch_failed", exc_info=True)
        return {}
    if token is None:
        return {}
    return getattr(token, "claims", {}) or {}


def _gate_email(claims: dict[str, Any]) -> str | None:
    """Email used for the org-domain gate decision — the email claim only, NEVER ``sub``.

    ``sub`` is always present when validation succeeds (google.py), so falling back to it would
    silently fail the ``@domain`` suffix match and deny the caller with a misleading "wrong domain"
    error. Absence of ``email`` is a distinct condition the caller handles explicitly.
    """
    return claims.get("email")


def _audit_user(claims: dict[str, Any]) -> str | None:
    """Best-effort identity (email, else subject) for the audit line's ``user`` field only."""
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
        claims = _get_claims()
        user = _audit_user(claims)  # attribution only (email else sub)
        gate_email = _gate_email(claims)  # decision only (email, no sub fallback)

        # Post-mint org gate (defense-in-depth), two distinct refusals — both logged:
        #   1. no email claim → can't evaluate the gate at all (auth/scope problem), fail loud.
        if gate_email is None:
            log.info(
                "tool_call",
                user=user,
                tool=tool,
                args_summary=args_summary,
                outcome="denied_no_email",
                duration_ms=0,
            )
            raise ToolError(
                "authenticated identity has no email claim; cannot evaluate org domain gate "
                "— check auth email scope/provider"
            )
        #   2. email present but outside the allowed domain → ordinary domain refusal.
        if not email_in_domain(gate_email, self._allowed_domain):
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
