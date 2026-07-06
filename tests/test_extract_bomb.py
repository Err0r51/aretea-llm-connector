"""AC10 + AC9(zip): the OOXML decompression-bomb ceiling and corrupt-zip detection."""

from __future__ import annotations

import io
import zipfile

import pytest
from aretea_drive_mcp.gdrive.extract import (
    ExtractionError,
    _guard_ooxml_bomb,
    extract_docx,
)


def _inflating_zip(uncompressed_mb: int) -> bytes:
    """A real (tiny-on-disk) zip whose single entry inflates to `uncompressed_mb` MB of zeros."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.bin", b"\0" * (uncompressed_mb * 1024 * 1024))
    return buf.getvalue()


def test_decompression_bomb_refused_within_ceiling() -> None:  # AC10
    with pytest.raises(ExtractionError) as exc:
        _guard_ooxml_bomb(_inflating_zip(8), ceiling=4 * 1024 * 1024)  # 8 MB inflate, 4 MB ceiling
    assert exc.value.reason == "decompression_bomb_refused"


def test_bomb_guard_is_wired_into_an_extractor() -> None:  # AC10 (through extract_docx)
    with pytest.raises(ExtractionError) as exc:
        extract_docx(_inflating_zip(8), max_uncompressed_bytes=4 * 1024 * 1024)
    assert exc.value.reason == "decompression_bomb_refused"


def test_non_zip_payload_is_corrupt() -> None:  # AC9 (OOXML corrupt)
    with pytest.raises(ExtractionError) as exc:
        _guard_ooxml_bomb(b"this is not a zip archive", ceiling=10_000)
    assert exc.value.reason == "corrupt"
