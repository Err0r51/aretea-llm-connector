"""AC10 — read_file refuses any file whose driveId != the AI-Visible drive, before content."""

from __future__ import annotations

import pytest
from aretea_drive_mcp.gdrive import client as client_mod
from aretea_drive_mcp.gdrive.client import DriveBoundaryError, DriveClient, assert_in_drive

DRIVE = "AI_VISIBLE_DRIVE"


def test_in_drive_file_is_allowed() -> None:
    assert_in_drive({"id": "1", "driveId": DRIVE}, DRIVE)  # no raise


def test_out_of_drive_file_is_refused() -> None:
    with pytest.raises(DriveBoundaryError):
        assert_in_drive({"id": "2", "driveId": "FINANCE_DRIVE"}, DRIVE)


def test_missing_driveid_is_refused() -> None:
    with pytest.raises(DriveBoundaryError):
        assert_in_drive({"id": "3"}, DRIVE)


@pytest.mark.asyncio
async def test_get_metadata_enforces_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    """The boundary is asserted before any content is returned (defense-in-depth)."""
    client = DriveClient.__new__(DriveClient)  # skip __init__ (no real creds needed)
    client.drive_id = DRIVE
    client._retries = 1  # type: ignore[attr-defined]

    async def fake_run_sync(fn, *args, **kwargs):  # noqa: ANN001, ANN202
        return {"id": "x", "driveId": "FINANCE_DRIVE", "mimeType": "text/plain"}

    monkeypatch.setattr(client_mod.anyio.to_thread, "run_sync", fake_run_sync)

    with pytest.raises(DriveBoundaryError):
        await client.get_metadata("x")
