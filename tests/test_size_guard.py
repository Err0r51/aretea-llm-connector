"""AC5/AC6/AC11: input-size guard refuses before download, fails safe, keeps the boundary."""

from __future__ import annotations

import pytest
from aretea_drive_mcp.gdrive import client as client_mod
from aretea_drive_mcp.gdrive.client import (
    SIZE_UNKNOWN_PLACEHOLDER,
    DriveBoundaryError,
    DriveClient,
    _oversize_verdict,
)

DRIVE = "AI_VISIBLE_DRIVE"
MIME_PDF = "application/pdf"
MIME_DOC = "application/vnd.google-apps.document"


# --- pure verdict (no client, no I/O) ---
def test_verdict_oversize_refuses() -> None:  # AC5
    assert _oversize_verdict({"size": "999999999"}, MIME_PDF, 1_000) is not None


def test_verdict_under_cap_proceeds() -> None:
    assert _oversize_verdict({"size": "500"}, MIME_PDF, 1_000) is None


def test_verdict_absent_size_fails_safe() -> None:  # AC6
    assert _oversize_verdict({}, MIME_PDF, 1_000) == SIZE_UNKNOWN_PLACEHOLDER


def test_verdict_native_google_type_is_exempt() -> None:
    # A native Doc is an export, not a get_media blob — not size-guarded here.
    assert _oversize_verdict({"size": "999999999"}, MIME_DOC, 1) is None


def test_verdict_text_file_is_guarded() -> None:
    # Plain text also flows through get_media, so it shares the guard (behavior change, PRD 5).
    assert _oversize_verdict({"size": "999999999"}, "text/plain", 1_000) is not None


# --- through read_file (async harness) ---
def _client() -> DriveClient:
    client = DriveClient.__new__(DriveClient)
    client.drive_id = DRIVE
    client._retries = 1  # type: ignore[attr-defined]
    client._max_input_bytes = 1_000  # type: ignore[attr-defined]
    client._max_uncompressed_bytes = 314_572_800  # type: ignore[attr-defined]
    return client


async def _meta(file_id: str, **extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": file_id,
        "driveId": DRIVE,
        "mimeType": MIME_PDF,
        "name": file_id,
    }
    base.update(extra)
    return base


@pytest.mark.asyncio
async def test_oversize_refused_without_downloading() -> None:  # AC5
    client = _client()
    downloads: list[str] = []

    async def fake_meta(file_id: str) -> dict[str, object]:
        return await _meta(file_id, size="5000")

    def track_download(file_id: str) -> bytes:
        downloads.append(file_id)
        return b"should-not-be-downloaded"

    client.get_metadata = fake_meta  # type: ignore[method-assign]
    client._get_media_bytes = track_download  # type: ignore[method-assign]

    result = await client.read_file("big")
    assert "size limit" in result["content"]
    assert downloads == []  # AC5: nothing was downloaded


@pytest.mark.asyncio
async def test_absent_size_fails_safe_without_downloading() -> None:  # AC6
    client = _client()
    downloads: list[str] = []

    async def fake_meta(file_id: str) -> dict[str, object]:
        return await _meta(file_id)  # no "size" key

    def track_download(file_id: str) -> bytes:
        downloads.append(file_id)
        return b"x"

    client.get_metadata = fake_meta  # type: ignore[method-assign]
    client._get_media_bytes = track_download  # type: ignore[method-assign]

    result = await client.read_file("mystery")
    assert result["content"] == SIZE_UNKNOWN_PLACEHOLDER
    assert downloads == []


@pytest.mark.asyncio
async def test_boundary_refuses_before_extraction(monkeypatch: pytest.MonkeyPatch) -> None:  # AC11
    client = _client()

    async def fake_run_sync(fn, *args, **kwargs):
        return {"id": "x", "driveId": "FINANCE_DRIVE", "mimeType": MIME_PDF, "size": "10"}

    monkeypatch.setattr(client_mod.anyio.to_thread, "run_sync", fake_run_sync)
    with pytest.raises(DriveBoundaryError):
        await client.read_file("x")
