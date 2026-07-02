"""AC9 — the SA credential uses no delegation/subject and exactly the three read scopes."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from aretea_drive_mcp.gdrive import credentials
from aretea_drive_mcp.gdrive.credentials import (
    READ_SCOPES,
    DelegationError,
    assert_no_delegation,
    build_credentials,
)


def test_exactly_three_read_only_scopes() -> None:
    assert len(READ_SCOPES) == 3
    assert all(scope.endswith(".readonly") for scope in READ_SCOPES)


def test_build_credentials_requests_the_read_scopes_and_no_subject() -> None:
    captured: dict[str, object] = {}

    class FakeCreds:
        _subject = None  # no domain-wide delegation

    def fake_from_info(info: dict, scopes: list[str]) -> FakeCreds:
        captured["info"] = info
        captured["scopes"] = scopes
        return FakeCreds()

    with patch.object(
        credentials.service_account.Credentials,
        "from_service_account_info",
        staticmethod(fake_from_info),
    ):
        build_credentials('{"type": "service_account", "project_id": "x"}')

    assert captured["scopes"] == list(READ_SCOPES)
    assert captured["info"] == {"type": "service_account", "project_id": "x"}


def test_assert_no_delegation_rejects_a_subject() -> None:
    class Impersonating:
        _subject = "user@aretea-group.com"

    with pytest.raises(DelegationError):
        assert_no_delegation(Impersonating())  # type: ignore[arg-type]
