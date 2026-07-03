"""Fix C — _is_export_size_error recognises Drive's 403 exportSizeLimitExceeded (so a huge Doc
degrades to a stated placeholder) but NOT a permission 403 (which must still refuse — AC10).

Own-invariant: we hand-construct a real googleapiclient HttpError from crafted error JSON so its
error_details/reason parse exactly as the library would — no Drive API is mocked.
"""

from __future__ import annotations

import json

from aretea_drive_mcp.gdrive.client import _is_export_size_error
from googleapiclient.errors import HttpError


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


def test_export_size_error_detected_via_reason_token() -> None:
    err = _http_error("exportSizeLimitExceeded", "This file is too large to be exported.")
    assert _is_export_size_error(err) is True


def test_permission_denied_is_not_treated_as_size_error() -> None:
    err = _http_error(
        "insufficientFilePermissions",
        "The user does not have sufficient permissions for file 123.",
    )
    assert _is_export_size_error(err) is False


def test_export_size_error_detected_via_message_fallback() -> None:
    # No `errors` list — only the English message. The fallback still catches it.
    content = json.dumps(
        {"error": {"code": 403, "message": "This file is too large to be exported."}}
    ).encode()
    err = HttpError(_Resp(403), content)
    assert _is_export_size_error(err) is True
