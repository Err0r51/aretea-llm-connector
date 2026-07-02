"""Persistent, encrypted token/registration storage for the FastMCP auth provider.

FastMCP's `client_storage` is an ``AsyncKeyValue`` (from ``py-key-value-aio``) — there is **no
SQLite backend** (PRD A1). We use a ``FileTreeStore`` on the Railway persistent volume so OAuth
tokens and DCR client registrations survive restarts, wrapped in a Fernet encryption layer.

Two things are *both* required for durability on Linux (PRD A1):
  1. a persistent backend on the volume (this file), and
  2. a **fixed** encryption key (``STORAGE_ENCRYPTION_KEY``) — the default salt is per-boot, so
     without a fixed key the ciphertext survives a restart but the key to read it does not.

⚠ The exact module paths below are from current py-key-value-aio docs; verify against the pinned
version at build (they are the one place the store wiring can drift).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cryptography.fernet import Fernet
from key_value.aio.stores.filetree import FileTreeStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

if TYPE_CHECKING:
    from aretea_drive_mcp.config import Settings


def make_store(settings: Settings) -> FernetEncryptionWrapper:
    """Build the encrypted, volume-backed key-value store passed to the auth provider.

    `STORAGE_ENCRYPTION_KEY` is a Fernet key (generate once with ``Fernet.generate_key()``); using
    a fixed key is what makes stored tokens survive a restart (PRD A1).
    """
    disk = FileTreeStore(data_directory=settings.storage_dir)
    fernet = Fernet(settings.storage_encryption_key.get_secret_value())
    return FernetEncryptionWrapper(disk, fernet=fernet)
