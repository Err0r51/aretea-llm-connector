"""Fix D — search() (a LIST endpoint) DROPS a stray out-of-drive row and keeps the good ones,
instead of raising and losing the whole result set. Single-file reads still refuse hard (see
test_ac10_driveid_assertion.py) — that behaviour is deliberately unchanged.

Own-invariant: reuse the DriveClient.__new__ + monkeypatched run_sync pattern; no Drive API call.
"""

from __future__ import annotations

import pytest
from aretea_drive_mcp.gdrive import client as client_mod
from aretea_drive_mcp.gdrive.client import DriveClient

DRIVE = "AI_VISIBLE_DRIVE"


@pytest.mark.asyncio
async def test_search_drops_out_of_drive_items_and_keeps_in_drive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DriveClient.__new__(DriveClient)  # skip __init__ (no real creds needed)
    client.drive_id = DRIVE
    client._retries = 1  # type: ignore[attr-defined]

    async def fake_run_sync(fn, *args, **kwargs):  # noqa: ANN001, ANN202
        return {
            "files": [
                {"id": "a", "driveId": DRIVE},  # kept
                {"id": "b", "driveId": "FINANCE_DRIVE"},  # dropped (wrong drive)
                {"id": "c"},  # dropped (missing driveId)
            ],
            "nextPageToken": "tok",
        }

    monkeypatch.setattr(client_mod.anyio.to_thread, "run_sync", fake_run_sync)

    result = await client.search("name contains 'x'")

    assert [f["id"] for f in result["files"]] == ["a"]  # only the in-drive row survives
    assert result["next_page_token"] == "tok"  # noqa: S105 (page token, not a secret)
