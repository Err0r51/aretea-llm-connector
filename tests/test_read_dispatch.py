"""AC1(wiring)/AC15: the sync _read_regular dispatch — registry routing and error propagation.

These exercise the download seam (`_get_media_bytes`, patched) rather than the pure extractors, so a
registry mis-key or a swallowed permission error is caught here — the pure fixture tests cannot see
either, since they never go through the dispatcher.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from aretea_drive_mcp.gdrive.client import DriveClient
from googleapiclient.errors import HttpError

MIME_PDF = "application/pdf"
PDF_FIXTURE = (pathlib.Path(__file__).parent / "fixtures" / "text_layer.pdf").read_bytes()


class _Resp:
    """Minimal httplib2-style response HttpError needs (.status, .reason)."""

    def __init__(self, status: int) -> None:
        self.status = status
        self.reason = "Forbidden"


def _http_error(reason_token: str, message: str) -> HttpError:
    content = json.dumps(
        {
            "error": {
                "code": 403,
                "message": message,
                "errors": [{"domain": "global", "reason": reason_token, "message": message}],
            }
        }
    ).encode()
    return HttpError(_Resp(403), content)


def _client() -> DriveClient:
    client = DriveClient.__new__(DriveClient)  # skip __init__ (no real creds needed)
    client._retries = 1  # type: ignore[attr-defined]
    client._max_uncompressed_bytes = 314_572_800  # type: ignore[attr-defined]
    return client


def test_pdf_mime_routes_to_pdf_extractor() -> None:  # AC1 (wiring)
    client = _client()

    def _bytes(file_id: str) -> bytes:
        return PDF_FIXTURE

    client._get_media_bytes = _bytes  # type: ignore[method-assign]
    text = client._read_regular("x", MIME_PDF)
    assert "Hello Aretea board deck" in text


def test_permission_403_propagates_and_is_not_swallowed() -> None:  # AC15
    client = _client()

    def _raise(file_id: str) -> bytes:
        raise _http_error("insufficientFilePermissions", "no permission for file x")

    client._get_media_bytes = _raise  # type: ignore[method-assign]
    with pytest.raises(HttpError):
        client._read_regular("x", MIME_PDF)
