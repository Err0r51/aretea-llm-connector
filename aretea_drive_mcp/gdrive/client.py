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
Google API. The pure per-format extractors in ``extract.py`` are unit-tested against real fixture
files, but the Drive method/field names themselves are only ``⚠ verify at build`` — no test
exercises the live Drive API.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import anyio
import httplib2
import structlog
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from aretea_drive_mcp.gdrive.credentials import build_credentials
from aretea_drive_mcp.gdrive.extract import (
    ExtractionError,
    extract_docx,
    extract_pdf,
    extract_pptx,
    extract_xlsx,
)

log = structlog.get_logger("gdrive.client")

# Native Google mime types we extract specially.
MIME_DOC = "application/vnd.google-apps.document"
MIME_SHEET = "application/vnd.google-apps.spreadsheet"
MIME_SLIDES = "application/vnd.google-apps.presentation"

# Modern OOXML Office types → pure in-process extractors (PRD 5). Binary content read via get_media.
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

# mime → pure extractor. Each takes ``(data: bytes, *, max_uncompressed_bytes: int) -> str`` and
# raises ExtractionError for expected-degraded cases; ``application/pdf`` ignores the ceiling kwarg.
EXTRACTORS: dict[str, Callable[..., str]] = {
    "application/pdf": extract_pdf,
    MIME_DOCX: extract_docx,
    MIME_XLSX: extract_xlsx,
    MIME_PPTX: extract_pptx,
}
# mime → log-outcome token for a successful extraction (observability; PRD 5).
_EXTRACT_OUTCOME = {
    "application/pdf": "pdf_text",
    MIME_DOCX: "docx",
    MIME_XLSX: "xlsx",
    MIME_PPTX: "pptx",
}

# Pre-2007 OLE binary Office formats — unsupported in v1 (need LibreOffice/antiword); placeholdered.
LEGACY_OLE_MIMES = frozenset(
    {"application/msword", "application/vnd.ms-excel", "application/vnd.ms-powerpoint"}
)

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

# Stated placeholders for the binary-extraction paths (PRD 5) — never silent (AC11 spirit).
LEGACY_PLACEHOLDER = (
    "[legacy Office format (.doc/.xls/.ppt) unsupported — re-save as .docx/.xlsx/.pptx to extract]"
)
SIZE_UNKNOWN_PLACEHOLDER = (
    "[file size is unknown — refusing to download it for extraction (fail-safe)]"
)


def _oversize_placeholder(cap_bytes: int) -> str:
    return (
        f"[file exceeds the {cap_bytes // (1024 * 1024)}-MB extraction size limit — not downloaded]"
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


def _needs_download(mime: str) -> bool:
    """True for the get_media reads (plain text + binary extractors) — the only paths that pull an
    unbounded raw blob, so the input-size guard applies to exactly these. Native Google types
    (Doc/Sheet/Slides) and unhandled binaries never reach a get_media download."""
    return _is_text_mime(mime) or mime in EXTRACTORS


def _oversize_verdict(file_meta: dict[str, Any], mime: str, cap_bytes: int) -> str | None:
    """Return a stated placeholder to refuse a download with, or None to proceed. Pure (AC5/AC6).

    Applied only to get_media paths. Drive reports ``size`` as a string; absent/unparseable → fail
    safe (refuse), since a get_media on the single worker has no other size backstop."""
    if not _needs_download(mime):
        return None
    try:
        size = int(file_meta.get("size"))  # type: ignore[arg-type]  # None → TypeError below
    except (TypeError, ValueError):
        return SIZE_UNKNOWN_PLACEHOLDER
    return _oversize_placeholder(cap_bytes) if size > cap_bytes else None


class DriveClient:
    """Read-only Google Drive access pinned to a single Shared Drive."""

    def __init__(
        self,
        sa_key_json: str,
        drive_id: str,
        num_retries: int = 5,
        max_input_bytes: int = 52_428_800,
        max_uncompressed_bytes: int = 314_572_800,
    ) -> None:
        self._creds = build_credentials(sa_key_json)
        self.drive_id = drive_id
        self._retries = num_retries
        self._max_input_bytes = max_input_bytes
        self._max_uncompressed_bytes = max_uncompressed_bytes

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
        """Return ``{mime_type, content, name}`` (str content). Tool applies truncation."""
        meta = await self.get_metadata(file_id)  # asserts in-drive before any content is fetched
        mime = meta.get("mimeType", "")

        # Input-size guard (PRD 5): refuse an oversized/unknown-size blob BEFORE downloading it, so
        # a large file can't OOM the single worker. Runs on the event loop — no offload, no bytes.
        verdict = _oversize_verdict(meta, mime, self._max_input_bytes)
        if verdict is not None:
            log.warning("drive.extract", file_id=file_id, mime=mime, outcome="oversize_refused")
            return {"mime_type": mime, "content": verdict, "name": meta.get("name")}

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

    def _get_media_bytes(self, file_id: str) -> bytes:
        """Download a file's raw bytes via get_media (read-only). Any HttpError (permission/boundary
        403/404) propagates unchanged — degradation must never mask a real access failure (AC15)."""
        svc = self._service("drive", "v3")
        data = (
            svc.files()
            .get_media(fileId=file_id, supportsAllDrives=True)
            .execute(num_retries=self._retries)
        )
        return data if isinstance(data, bytes) else bytes(data)

    def _read_regular(self, file_id: str, mime: str) -> str:
        """Sync dispatch for non-native reads: plain text, PDF/OOXML extraction, or a stated
        placeholder. Synchronous with the download isolated in ``_get_media_bytes`` so unit tests
        drive the registry wiring and error propagation directly. Runs inside read_file's offload.
        """
        if _is_text_mime(mime):
            return self._get_media_bytes(file_id).decode("utf-8", "replace")
        if mime in LEGACY_OLE_MIMES:
            log.info("drive.extract", file_id=file_id, mime=mime, outcome="legacy_unsupported")
            return LEGACY_PLACEHOLDER
        extractor = EXTRACTORS.get(mime)
        if extractor is None:
            return BINARY_PLACEHOLDER
        data = self._get_media_bytes(file_id)  # HttpError propagates (AC15) — outside the try below
        try:
            text = extractor(data, max_uncompressed_bytes=self._max_uncompressed_bytes)
        except ExtractionError as err:
            log.warning("drive.extract", file_id=file_id, mime=mime, outcome=err.reason)
            return err.placeholder
        log.info("drive.extract", file_id=file_id, mime=mime, outcome=_EXTRACT_OUTCOME[mime])
        return text
