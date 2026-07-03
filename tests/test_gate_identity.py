"""Fix B — the org gate reads the email claim (never sub), and a token with no email claim is
refused with a DISTINCT, loud error instead of a misleading "wrong domain" denial.

Invariant-only: we monkeypatch OUR get_access_token accessor, not Google. These assert how our
middleware extracts identity and branches — not that FastMCP/Google populate the claim.
"""

from __future__ import annotations

import pytest
from aretea_drive_mcp import audit as audit_mod
from aretea_drive_mcp.audit import (
    AuditMiddleware,
    _audit_user,
    _gate_email,
    _get_claims,
)
from fastmcp.exceptions import ToolError


class FakeToken:
    def __init__(self, claims: dict) -> None:
        self.claims = claims


class _Msg:
    name = "drive_search"
    arguments: dict = {"query": "budget"}


class _Ctx:
    message = _Msg()


def test_gate_email_ignores_sub() -> None:
    # sub is always present; the gate must NOT fall back to it (would misleadingly deny).
    assert _gate_email({"sub": "12345"}) is None


def test_gate_email_returns_email_when_present() -> None:
    assert _gate_email({"email": "a@aretea-group.com", "sub": "1"}) == "a@aretea-group.com"


def test_audit_user_still_falls_back_to_sub() -> None:
    # The audit LINE keeps best-effort attribution (email else sub).
    assert _audit_user({"sub": "12345"}) == "12345"
    assert _audit_user({"email": "a@x", "sub": "1"}) == "a@x"


def test_get_claims_no_token_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit_mod, "get_access_token", lambda: None)
    assert _get_claims() == {}


def test_get_claims_swallows_and_logs_not_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> None:
        raise RuntimeError("auth layer exploded")

    monkeypatch.setattr(audit_mod, "get_access_token", boom)
    assert _get_claims() == {}  # logged as auth.token_fetch_failed, not raised


@pytest.mark.asyncio
async def test_no_email_claim_raises_distinct_error_and_does_not_run_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(audit_mod, "get_access_token", lambda: FakeToken({"sub": "12345"}))
    mw = AuditMiddleware("aretea-group.com")
    called = False

    async def call_next(_ctx: object) -> str:
        nonlocal called
        called = True
        return "SHOULD_NOT_RUN"

    with pytest.raises(ToolError, match="email claim"):
        await mw.on_call_tool(_Ctx(), call_next)
    assert called is False


@pytest.mark.asyncio
async def test_in_domain_email_passes_gate_and_runs_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        audit_mod,
        "get_access_token",
        lambda: FakeToken({"email": "a@aretea-group.com", "sub": "1"}),
    )
    mw = AuditMiddleware("aretea-group.com")

    async def call_next(_ctx: object) -> str:
        return "RESULT"

    assert await mw.on_call_tool(_Ctx(), call_next) == "RESULT"
