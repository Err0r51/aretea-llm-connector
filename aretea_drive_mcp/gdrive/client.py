"""Scoped, boundary-checked access to Drive v3 / Sheets v4 / Slides v1.

Two invariants make this safe (PRD FR5):
  1. Every query is pinned to the one AI-Visible Shared Drive (``corpora=drive``, ``driveId=...``).
  2. Before any file's content is returned, its ``driveId`` is asserted equal to the allowed drive
     (``assert_in_drive``) — defense-in-depth against a scoping bug (AC10).

Concurrency (see ARCHITECTURE §3): ``google-api-python-client`` is **blocking** and
``httplib2.Http`` is **not thread-safe**. Public methods are ``async`` and offload blocking work
to a worker thread via ``anyio.to_thread.run_sync``; each threaded call builds its **own** service
on a fresh authorized http. The credentials object is shared (that is safe).

⚠ Method/field names (``export_media``, ``get_media``, Slides shape walk) are written to the current
Google API and unit-tested against ``HttpMock``; verify against the live API at build.
"""

from __future__ import annotations

from typing import Any, cast

import anyio
import httplib2
import structlog
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from aretea_drive_mcp.gdrive.credentials import build_credentials

log = structlog.get_logger("gdrive.client")

# Native Google mime types we extract specially.
MIME_DOC = "application/vnd.google-apps.document"
MIME_SHEET = "application/vnd.google-apps.spreadsheet"
MIME_SLIDES = "application/vnd.google-apps.presentation"

# Fields fetched for every file — driveId is required for the boundary assertion.
FILE_FIELDS = (
    "id,name,mimeType,modifiedTime,owners(displayName,emailAddress),webViewLink,size,driveId"
)

BINARY_PLACEHOLDER = "[binary — not text-extracted in v1]"

# Drive's REST files.export endpoint caps plain-text export at ~10 MB and returns a 403
# `exportSizeLimitExceeded` before any bytes. We surface that as stated content (like
# BINARY_PLACEHOLDER) so a huge Doc degrades gracefully instead of raising (AC11 — never silent).
EXPORT_TOO_LARGE_PLACEHOLDER = (
    "[truncated — this Google Doc exceeds Drive's 10 MB plain-text export limit and could not be "
    "exported as text; open it in Google Docs to read the full content]"
)


class DriveBoundaryError(RuntimeError):
    """Raised when a file's driveId is not the AI-Visible drive — refuse before returning it."""


def _is_export_size_error(err: HttpError) -> bool:
    """True iff `err` is Drive's 403 ``exportSizeLimitExceeded`` (Doc too large to export as text).

    Matches on the machine reason token (stable, in ``error_details``) with the English message as a
    weak fallback — never on the bare 403 status, so genuine permission/boundary 403s still refuse.
    """
    details = getattr(err, "error_details", None)
    if isinstance(details, list) and any(
        isinstance(d, dict) and d.get("reason") == "exportSizeLimitExceeded" for d in details
    ):
        return True
    return "too large to be exported" in (err.reason or "").lower()


def assert_in_drive(file_meta: dict[str, Any], expected_drive_id: str) -> None:
    """Fail if `file_meta` is not in the allowed drive (AC10). Pure — unit-testable without I/O."""
    if file_meta.get("driveId") != expected_drive_id:
        raise DriveBoundaryError(
            f"file {file_meta.get('id')!r} is outside the AI-Visible drive; refusing"
        )


def _is_text_mime(mime: str) -> bool:
    return mime.startswith("text/") or mime in {
        "application/json",
        "application/xml",
        "application/x-yaml",
        "application/csv",
    }


class DriveClient:
    """Read-only Google Drive access pinned to a single Shared Drive."""

    def __init__(self, sa_key_json: str, drive_id: str, num_retries: int = 5) -> None:
        self._creds = build_credentials(sa_key_json)
        self.drive_id = drive_id
        self._retries = num_retries

    # --- service builders (called inside worker threads; fresh http each time) ---
    def _http(self) -> AuthorizedHttp:
        return AuthorizedHttp(self._creds, http=httplib2.Http())

    def _service(self, name: str, version: str) -> Any:
        return build(name, version, http=self._http(), static_discovery=True)

    # --- public async API ---
    async def search(
        self, query: str, page_size: int = 25, page_token: str | None = None
    ) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            svc = self._service("drive", "v3")
            resp = (
                svc.files()
                .list(
                    q=query,
                    corpora="drive",
                    driveId=self.drive_id,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                    pageSize=page_size,
                    pageToken=page_token,
                    fields=f"nextPageToken,files({FILE_FIELDS})",
                )
                .execute(num_retries=self._retries)
            )
            return cast("dict[str, Any]", resp)

        resp = await anyio.to_thread.run_sync(_call)
        raw_files = resp.get("files", [])
        files: list[dict[str, Any]] = []
        for f in raw_files:
            # corpora="drive"+driveId already restricts results to this drive; this loop is
            # defense-in-depth. On a LIST endpoint, DROP a stray item (don't abort every good
            # result) but log it so a real scoping breach can't hide silently. (Single-file
            # get_metadata/read_file still RAISE — see assert_in_drive callers below.)
            if f.get("driveId") == self.drive_id:
                files.append(f)
            else:
                log.warning(
                    "drive.search.dropped_out_of_drive_item",
                    file_id=f.get("id"),
                    found_drive_id=f.get("driveId"),
                    expected_drive_id=self.drive_id,
                )
        return {"files": files, "next_page_token": resp.get("nextPageToken")}

    async def get_metadata(self, file_id: str) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            svc = self._service("drive", "v3")
            resp = (
                svc.files()
                .get(fileId=file_id, fields=FILE_FIELDS, supportsAllDrives=True)
                .execute(num_retries=self._retries)
            )
            return cast("dict[str, Any]", resp)

        meta = await anyio.to_thread.run_sync(_call)
        assert_in_drive(meta, self.drive_id)
        return meta

    async def read_file(
        self, file_id: str, sheet: str | None = None, cell_range: str | None = None
    ) -> dict[str, Any]:
        """Return ``{mime_type, content}`` (str content). Truncation is applied by the tool."""
        meta = await self.get_metadata(file_id)  # asserts in-drive before any content is fetched
        mime = meta.get("mimeType", "")

        def _extract() -> str:
            if mime == MIME_DOC:
                return self._read_doc(file_id)
            if mime == MIME_SHEET:
                return self._read_sheet(file_id, sheet, cell_range)
            if mime == MIME_SLIDES:
                return self._read_slides(file_id)
            return self._read_regular(file_id, mime)

        content = await anyio.to_thread.run_sync(_extract)
        return {"mime_type": mime, "content": content, "name": meta.get("name")}

    # --- per-format extraction (sync; run inside a worker thread) ---
    def _read_doc(self, file_id: str) -> str:
        svc = self._service("drive", "v3")
        try:
            data = (
                svc.files()
                .export_media(fileId=file_id, mimeType="text/plain")
                .execute(num_retries=self._retries)
            )
        except HttpError as err:
            # Doc too large to export as text → stated placeholder, not a crash (AC11). Any other
            # HTTP error (permission/boundary 403/404, etc.) must still propagate and refuse (AC10).
            if _is_export_size_error(err):
                log.warning(
                    "drive.export_size_limit_exceeded",
                    file_id=file_id,
                    status=err.status_code,
                    reason=err.reason,
                )
                return EXPORT_TOO_LARGE_PLACEHOLDER
            raise
        return data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)

    def _read_sheet(self, file_id: str, sheet: str | None, cell_range: str | None) -> str:
        svc = self._service("sheets", "v4")
        if cell_range:
            ranges = [cell_range]
        elif sheet:
            ranges = [sheet]
        else:
            meta = (
                svc.spreadsheets()
                .get(spreadsheetId=file_id, fields="sheets.properties.title")
                .execute(num_retries=self._retries)
            )
            ranges = [s["properties"]["title"] for s in meta.get("sheets", [])]

        batch = (
            svc.spreadsheets()
            .values()
            .batchGet(
                spreadsheetId=file_id,
                ranges=ranges,
                valueRenderOption="UNFORMATTED_VALUE",  # values only, never formulas
            )
            .execute(num_retries=self._retries)
        )
        parts: list[str] = []
        for vr in batch.get("valueRanges", []):
            parts.append(f"# {vr.get('range', '')}")
            for row in vr.get("values", []):
                parts.append("\t".join("" if c is None else str(c) for c in row))
        return "\n".join(parts)

    def _read_slides(self, file_id: str) -> str:
        svc = self._service("slides", "v1")
        pres = svc.presentations().get(presentationId=file_id).execute(num_retries=self._retries)
        lines: list[str] = []
        for i, slide in enumerate(pres.get("slides", []), start=1):
            lines.append(f"--- Slide {i} ---")
            for element in slide.get("pageElements", []):
                text = element.get("shape", {}).get("text")
                if not text:
                    continue
                for te in text.get("textElements", []):
                    content = te.get("textRun", {}).get("content")
                    if content and content.strip():
                        lines.append(content.rstrip("\n"))
        return "\n".join(lines)

    def _read_regular(self, file_id: str, mime: str) -> str:
        if not _is_text_mime(mime):
            return BINARY_PLACEHOLDER
        svc = self._service("drive", "v3")
        data = (
            svc.files()
            .get_media(fileId=file_id, supportsAllDrives=True)
            .execute(num_retries=self._retries)
        )
        return data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)
