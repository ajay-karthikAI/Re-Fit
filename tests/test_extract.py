from pathlib import Path

import pymupdf
import pytest

from app.services.errors import FileTooLargeError, UnsupportedFormatError
from app.services.extract import MAX_UPLOAD_BYTES, extract_text

CORPUS_RESUMES = Path(__file__).parent / "corpus" / "resumes"


def _corpus_files() -> list[Path]:
    return sorted(p for p in CORPUS_RESUMES.iterdir() if p.suffix.lower() in {".pdf", ".docx"})


@pytest.mark.parametrize("path", _corpus_files(), ids=lambda p: p.name)
def test_corpus_file_extracts(path: Path) -> None:
    result = extract_text(path.read_bytes(), path.name)
    # Real scanned PDFs may yield no text — then the warning must say so.
    assert result.raw_text.strip() or result.extraction_warnings, path.name
    assert result.source_format == path.suffix.lstrip(".").lower()
    if result.source_format == "pdf":
        assert result.page_count is not None and result.page_count >= 1
    else:
        assert result.page_count is None
    assert "\x00" not in result.raw_text


def test_two_column_pdf_reading_order_not_interleaved() -> None:
    path = CORPUS_RESUMES / "synthetic_two_column.pdf"
    result = extract_text(path.read_bytes(), path.name)
    text = result.raw_text

    # Phrases that span a full line inside one column must survive contiguously —
    # naive extraction interleaves the two columns mid-sentence.
    for phrase in [
        "Moved ingestion from cron to Dagster; 99.7% on-time runs",
        "Python, SQL, dbt, Dagster, Snowflake, Airflow, Terraform, Looker",
        "jordan.rivera@example.com | (555) 013-7788 | Austin, TX",
    ]:
        assert phrase in text, f"phrase split apart:\n{text}"

    # Reading order: contact header before experience, dates not dumped at the top.
    assert text.index("jordan.rivera@example.com") < text.index("Data Engineer")
    assert not text.startswith("2021-08")


def test_docx_includes_tables_and_headers() -> None:
    path = CORPUS_RESUMES / "synthetic_table_layout.docx"
    result = extract_text(path.read_bytes(), path.name)
    assert "sam.okafor@example.com" in result.raw_text  # page header
    assert "Nimbus Freight" in result.raw_text  # table cell
    assert result.extraction_warnings == []


@pytest.fixture
def image_only_pdf() -> bytes:
    """A one-page PDF with drawings but no extractable text (a scan stand-in)."""
    doc = pymupdf.open()
    page = doc.new_page()
    shape = page.new_shape()
    shape.draw_rect(pymupdf.Rect(50, 50, 500, 700))
    shape.finish(fill=(0.85, 0.85, 0.85))
    shape.commit()
    data = doc.tobytes()
    doc.close()
    return data


def test_image_only_pdf_warns(image_only_pdf: bytes) -> None:
    result = extract_text(image_only_pdf, "scan.pdf")
    assert result.extraction_warnings == ["page 1 appears image-based (possible scan)"]
    assert result.page_count == 1


def test_unsupported_format_rejected() -> None:
    with pytest.raises(UnsupportedFormatError, match="only .pdf and .docx"):
        extract_text(b"plain text", "resume.txt")


def test_oversized_file_rejected() -> None:
    with pytest.raises(FileTooLargeError, match="10 MB"):
        extract_text(b"x" * (MAX_UPLOAD_BYTES + 1), "big.pdf")


def test_corrupt_pdf_rejected() -> None:
    with pytest.raises(UnsupportedFormatError, match="could not be parsed"):
        extract_text(b"%PDF-not really a pdf", "broken.pdf")
