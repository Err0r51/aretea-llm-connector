"""AC8: legacy OLE Office mimes (.doc/.xls/.ppt) return a stated placeholder, no download."""

from __future__ import annotations

import pytest
from aretea_drive_mcp.gdrive.client import LEGACY_OLE_MIMES, LEGACY_PLACEHOLDER, DriveClient


def _client() -> DriveClient:
    client = DriveClient.__new__(DriveClient)
    client._retries = 1  # type: ignore[attr-defined]
    client._max_uncompressed_bytes = 314_572_800  # type: ignore[attr-defined]
    return client


@pytest.mark.parametrize("mime", sorted(LEGACY_OLE_MIMES))
def test_legacy_mime_placeholdered_without_download(mime: str) -> None:
    client = _client()
    downloads: list[str] = []

    def track(file_id: str) -> bytes:
        downloads.append(file_id)
        return b"unused"

    client._get_media_bytes = track  # type: ignore[method-assign]
    assert client._read_regular("x", mime) == LEGACY_PLACEHOLDER
    assert downloads == []  # legacy formats are refused before any get_media
