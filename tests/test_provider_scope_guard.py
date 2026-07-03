"""Fix B — build_provider fails loudly at boot if the identity scopes drop the email claim the
org gate depends on (rather than denying every tool call at runtime)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from aretea_drive_mcp.auth import provider as provider_mod
from aretea_drive_mcp.auth.provider import build_provider


def test_build_provider_requires_email_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate the one config edit that would break email delivery.
    monkeypatch.setattr(provider_mod, "IDENTITY_SCOPES", ["openid", "profile"])
    # The guard fires before GoogleProvider is constructed, so settings is never dereferenced.
    with pytest.raises(RuntimeError, match="email"):
        build_provider(MagicMock())
