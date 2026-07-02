"""Service-account credentials for the Drive hop — read-only, no delegation.

The data boundary is the service account's Shared-Drive *membership* (NFR1), so the credential is
deliberately minimal: three read-only scopes and, critically, **no domain-wide delegation** — we
never call ``with_subject(...)``, which is the impersonation switch (AC9).
"""

from __future__ import annotations

import json

from google.oauth2 import service_account

# All read-only. `drive.readonly` alone can 403 the Sheets/Slides APIs, so we also request their
# read scopes — keeping the read-only principle while letting the Sheets/Slides calls work.
READ_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/presentations.readonly",
)


class DelegationError(RuntimeError):
    """Raised if a credential carries a delegation subject — a forbidden impersonation (AC9)."""


def assert_no_delegation(creds: service_account.Credentials) -> None:
    """Fail loudly if the credential impersonates a user (domain-wide delegation).

    Expressed as an explicit raise (not `assert`) so it holds under ``python -O`` too.
    """
    if getattr(creds, "_subject", None) is not None:
        raise DelegationError("service-account credential must not use with_subject / delegation")


def build_credentials(sa_key_json: str) -> service_account.Credentials:
    """Load the SA key JSON (from an env var) and return read-only, non-delegated credentials."""
    info = json.loads(sa_key_json)
    # from_service_account_info is untyped in google-auth; annotate the result explicitly.
    creds: service_account.Credentials = service_account.Credentials.from_service_account_info(  # type: ignore[no-untyped-call]
        info, scopes=list(READ_SCOPES)
    )
    assert_no_delegation(creds)
    return creds
