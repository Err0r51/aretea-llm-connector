"""Idempotent storage initialization — run in the start command, not the build.

Railway volumes mount at runtime (as root) and are absent at build time, so the storage directory
for the FileTreeStore must be created when the container starts:

    python -m aretea_drive_mcp.init_db && uvicorn aretea_drive_mcp.main:app --port $PORT
"""

from __future__ import annotations

import pathlib

from aretea_drive_mcp.config import get_settings


def main() -> None:
    settings = get_settings()
    path = pathlib.Path(settings.storage_dir)
    path.mkdir(parents=True, exist_ok=True)
    print(f"storage dir ready: {path}")


if __name__ == "__main__":
    main()
