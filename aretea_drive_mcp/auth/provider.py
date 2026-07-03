"""Client-hop authorization: FastMCP GoogleProvider (identity only) + org domain gate.

FastMCP's ``GoogleProvider`` bundles an ``OAuthProxy`` DCR-face with Google's token verifier and
**mints/verifies its own bearer token** — we write no JWT code. We request only ``openid email
profile``; the user is granted **zero Drive scopes** (FR2′).

Org gate — two layers (PRD A2):
  1. PRIMARY, Google-side: the Google OAuth app is set to *Internal* (Workspace-only), so a
     non-Aretea identity never receives an auth code → no token is minted. This is what satisfies
     AC3's "no token issued"; it is a Google console setting, not code here.
  2. DEFENSE-IN-DEPTH, here (post-mint): `require_domain` refuses any session whose email claim is
     outside the allowed domain → "no data reachable". `hd`/`email_verified` are NOT in the default
     claims, so we match on the email suffix.

⚠ The GoogleProvider kwargs and the domain-check hook shape are written to the documented FastMCP
3.x API; verify against fastmcp 3.4.2 at build/spike (the exact wiring is medium-confidence and the
whole client hop is spike-gated per PRD Phase 1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp.server.auth.providers.google import GoogleProvider

from aretea_drive_mcp.auth.store import make_store

if TYPE_CHECKING:
    from aretea_drive_mcp.config import Settings

# Identity only — NO Drive scopes are ever requested of the user (FR2′).
IDENTITY_SCOPES = ["openid", "email", "profile"]


def email_in_domain(email: str | None, allowed_domain: str) -> bool:
    """True iff `email` is a well-formed address inside `allowed_domain` (case-insensitive).

    The post-mint org gate. Kept pure so it is unit-testable without any OAuth flow (AC3 code side).
    """
    if not email:
        return False
    suffix = "@" + allowed_domain.lower().lstrip("@")
    return email.strip().lower().endswith(suffix)


def build_provider(settings: Settings) -> GoogleProvider:
    """Construct the identity-only Google auth provider with persistent, encrypted storage."""
    # Boot-time guard: the org gate reads the token's `email` claim, which only exists because we
    # request the email scope. Fail loudly at startup on the one edit that would drop it, rather
    # than denying every tool call at runtime with a misleading "no email claim" error.
    if "email" not in IDENTITY_SCOPES:
        raise RuntimeError(
            "identity scopes must include 'email' — the org domain gate depends on the email claim"
        )
    return GoogleProvider(
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret.get_secret_value(),
        base_url=settings.public_server_url,
        required_scopes=IDENTITY_SCOPES,
        # Fixed key so the minted bearer token survives restarts (not derived per-boot).
        jwt_signing_key=settings.jwt_signing_key.get_secret_value(),
        # Encrypted, volume-backed persistence for tokens + DCR client registrations.
        client_storage=make_store(settings),
    )
