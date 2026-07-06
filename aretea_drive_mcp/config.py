"""Boot-time configuration and secrets.

All settings load from the environment (Railway vars / 1Password) and are validated once at
startup, so a missing or malformed secret fails fast rather than at first request. Sensitive
values are `SecretStr` so they never render in logs or tracebacks.
"""

from __future__ import annotations

import functools

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
    )

    # --- Drive hop (service account) ---
    google_sa_key_json: SecretStr = Field(
        ..., description="Service-account key JSON (the whole document, as a string)."
    )
    ai_visible_drive_id: str = Field(
        ..., description="The single Shared Drive the SA may read. The data boundary."
    )

    # --- Client hop (identity-only OIDC via FastMCP GoogleProvider) ---
    google_oauth_client_id: str
    google_oauth_client_secret: SecretStr
    public_server_url: str = Field(
        ...,
        description="Exact deployed HTTPS URL. Must equal the RFC 9728 PRM `resource`.",
    )
    allowed_email_domain: str = Field(
        default="aretea-group.com",
        description="Post-mint gate: sessions whose email is outside this domain are refused.",
    )

    # --- Fixed secrets (must survive restart; NOT per-boot) ---
    jwt_signing_key: SecretStr = Field(
        ...,
        description="FastMCP mints/verifies our bearer token with this. Fixed, or tokens die.",
    )
    storage_encryption_key: SecretStr = Field(
        ...,
        description="Fernet key for at-rest token storage (A1). Fixed — else salt is ephemeral.",
    )

    # --- Storage / read guardrails ---
    storage_dir: str = Field(
        default="/data/storage",
        description="Directory on the Railway persistent volume for FileTreeStore.",
    )
    max_read_chars: int = Field(
        default=200_000,
        description="Per-read output cap (chars). Over this, output is truncated with a note.",
    )
    drive_num_retries: int = Field(
        default=5, description="google-api-python-client execute(num_retries=) for 429/5xx backoff."
    )
    max_input_bytes: int = Field(
        default=52_428_800,  # 50 MiB
        description=(
            "Refuse-before-download cap (bytes) for get_media extraction paths (PDF/OOXML/text). "
            "The single worker has no other backstop against an oversized blob (PRD 5)."
        ),
    )
    max_uncompressed_bytes: int = Field(
        default=314_572_800,  # 300 MiB
        description=(
            "OOXML decompression-bomb ceiling (bytes): total uncompressed zip size before refusal."
        ),
    )


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache settings. Call once at boot; raises on any missing/invalid var."""
    return Settings()  # values come from the environment (pydantic-settings)
