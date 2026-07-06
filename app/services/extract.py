"""Deterministic raw-text extraction from uploaded resume files.

PDF via pymupdf (blocks re-sorted into reading order so multi-column layouts
don't interleave mid-sentence), DOCX via docx2python (whose text output
includes tables, headers, and footers). No OCR in this phase — image-based
pages produce a warning instead.
"""

import re
from io import BytesIO

import pymupdf
from docx2python import docx2python

from app.schemas.extract import ExtractedText
from app.services.errors import FileTooLargeError, UnsupportedFormatError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MIN_PAGE_CHARS = 50
"""Below this many extracted chars, a PDF page is presumed image-based."""

_BAND_TOLERANCE = 12.0
"""Blocks whose y0 differ by less than this (in points) share a horizontal band."""


def _sorted_blocks(blocks: list[tuple]) -> list[tuple]:
    """Order text blocks top-to-bottom, left-to-right within horizontal bands.

    A plain (y, x) sort is enough for single-column pages; the banding keeps
    side-by-side blocks (two-column layouts, right-floated dates) from
    interleaving with unrelated rows.
    """
    text_blocks = sorted((b for b in blocks if b[6] == 0 and b[4].strip()), key=lambda b: b[1])
    bands: list[list[tuple]] = []
    for block in text_blocks:
        if bands and block[1] - bands[-1][0][1] < _BAND_TOLERANCE:
            bands[-1].append(block)
        else:
            bands.append([block])
    ordered: list[tuple] = []
    for band in bands:
        ordered.extend(sorted(band, key=lambda b: (b[0], b[1])))
    return ordered


def _normalize(text: str) -> str:
    """Cleanup that must not destroy structure signals.

    Bullet glyphs (•, -, *) are preserved on purpose — the LLM parser uses
    them to find list items.
    """
    text = text.replace("\x00", "")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{4,}", "\n\n\n", text)  # collapse >2 consecutive blank lines
    return text.strip()


def _extract_pdf(file_bytes: bytes) -> ExtractedText:
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        raise UnsupportedFormatError(f"file could not be parsed as PDF: {exc}") from exc

    warnings: list[str] = []
    pages: list[str] = []
    with doc:
        page_count = doc.page_count
        for index, page in enumerate(doc, start=1):
            # A block is a paragraph; its internal newlines are visual line
            # wraps, so re-join them to keep sentences contiguous.
            page_text = "\n".join(
                " ".join(line.strip() for line in block[4].splitlines() if line.strip())
                for block in _sorted_blocks(page.get_text("blocks"))
            )
            if len(page_text) < MIN_PAGE_CHARS:
                warnings.append(f"page {index} appears image-based (possible scan)")
            pages.append(page_text)

    return ExtractedText(
        raw_text=_normalize("\n\n".join(pages)),
        page_count=page_count,
        source_format="pdf",
        extraction_warnings=warnings,
    )


def _extract_docx(file_bytes: bytes) -> ExtractedText:
    try:
        with docx2python(BytesIO(file_bytes)) as doc:
            # .text includes body tables plus headers and footers.
            raw_text = doc.text
    except Exception as exc:
        raise UnsupportedFormatError(f"file could not be parsed as DOCX: {exc}") from exc

    warnings: list[str] = []
    if not raw_text.strip():
        warnings.append("document contains no extractable text")

    return ExtractedText(
        raw_text=_normalize(raw_text),
        page_count=None,
        source_format="docx",
        extraction_warnings=warnings,
    )


def extract_text(file_bytes: bytes, filename: str) -> ExtractedText:
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise FileTooLargeError(
            f"file is {len(file_bytes)} bytes; the limit is {MAX_UPLOAD_BYTES} (10 MB)"
        )

    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix == "pdf":
        return _extract_pdf(file_bytes)
    if suffix == "docx":
        return _extract_docx(file_bytes)
    raise UnsupportedFormatError(
        f"unsupported file type {suffix or '(none)'!r}: only .pdf and .docx are accepted"
    )
