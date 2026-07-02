"""AC3 (code side) — the post-mint org gate accepts only @aretea-group.com identities.

The "no token issued" half of AC3 rests on the Google OAuth app being Internal (Workspace-only) —
a console setting, verified in the Phase-1 spike, not here. This tests the "no data reachable"
defense-in-depth check.
"""

from __future__ import annotations

import pytest
from aretea_drive_mcp.auth.provider import email_in_domain

DOMAIN = "aretea-group.com"


@pytest.mark.parametrize(
    ("email", "allowed"),
    [
        ("alice@aretea-group.com", True),
        ("Alice@Aretea-Group.com", True),  # case-insensitive
        ("  bob@aretea-group.com  ", True),  # trimmed
        ("mallory@evil.com", False),
        ("mallory@sub.aretea-group.com", False),  # subdomain is NOT the org domain
        ("aretea-group.com", False),  # missing @, not an address in the domain
        ("x@aretea-group.com.evil.com", False),  # suffix-spoofing attempt
        (None, False),
        ("", False),
    ],
)
def test_email_in_domain(email: str | None, allowed: bool) -> None:
    assert email_in_domain(email, DOMAIN) is allowed
