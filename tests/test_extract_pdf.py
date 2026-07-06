"""AC1/AC7/AC9(pdf): extract_pdf against real PDFs — text-layer, scanned, corrupt, encrypted.

The text-layer PDF is a committed fixture (pypdf cannot author a text layer); the no-text-layer and
encrypted cases are generated in-test with pypdf's own writer.
"""

from __future__ import annotations

import io
import pathlib

import pytest
from aretea_drive_mcp.gdrive.extract import ExtractionError, extract_pdf
from pypdf import PdfWriter

CEIL = 314_572_800
FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "text_layer.pdf"


def _blank_pdf(*, encrypt: bool = False) -> bytes:
    """A one-page PDF with no text layer (a scanned-style document); optionally encrypted."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    if encrypt:
        writer.encrypt("pw")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_text_layer_pdf_returns_its_text() -> None:  # AC1
    text = extract_pdf(FIXTURE.read_bytes(), max_uncompressed_bytes=CEIL)
    assert "Hello Aretea board deck" in text
    assert "Q3 revenue up 12 percent" in text


def test_no_text_layer_pdf_is_stated_not_crashed() -> None:  # AC7
    with pytest.raises(ExtractionError) as exc:
        extract_pdf(_blank_pdf(), max_uncompressed_bytes=CEIL)
    assert exc.value.reason == "no_text_layer"


def test_corrupt_pdf_is_stated() -> None:  # AC9
    with pytest.raises(ExtractionError) as exc:
        extract_pdf(b"%PDF-1.4 not really a valid pdf body", max_uncompressed_bytes=CEIL)
    assert exc.value.reason == "corrupt"


def test_encrypted_pdf_is_stated() -> None:  # AC9
    with pytest.raises(ExtractionError) as exc:
        extract_pdf(_blank_pdf(encrypt=True), max_uncompressed_bytes=CEIL)
    assert exc.value.reason == "encrypted"
