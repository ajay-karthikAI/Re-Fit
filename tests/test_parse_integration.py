"""End-to-end parser tests against the real OpenAI API.

Skipped when no usable OPENAI_API_KEY is available (unset, or still the
.env placeholder). These cost real tokens.
"""

import os
from pathlib import Path

import pytest

from app.config import get_settings
from app.schemas.parse import ParseResult
from app.services.extract import extract_text
from app.services.parser import parse_resume

CORPUS_RESUMES = Path(__file__).parent / "corpus" / "resumes"
_PLACEHOLDER_KEYS = {"", "changeme"}


def _api_key_available() -> bool:
    env_key = os.environ.get("OPENAI_API_KEY", "")
    settings_key = get_settings().openai_api_key
    return env_key not in _PLACEHOLDER_KEYS or settings_key not in _PLACEHOLDER_KEYS


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _api_key_available(), reason="OPENAI_API_KEY is unset"),
]


async def _parse_corpus_file(filename: str) -> ParseResult:
    path = CORPUS_RESUMES / filename
    extracted = extract_text(path.read_bytes(), path.name)
    return await parse_resume(extracted)


def _drift_notes(result: ParseResult) -> list[str]:
    return [n for n in result.confidence_notes if n.startswith("possible paraphrase drift")]


async def test_parse_two_column_pdf_end_to_end() -> None:
    result = await _parse_corpus_file("synthetic_two_column.pdf")
    assert result.resume.contact.email == "jordan.rivera@example.com"
    assert len(result.resume.experience) >= 1
    assert result.usage.input_tokens > 0
    assert result.usage.output_tokens > 0


async def test_parse_table_docx_end_to_end_and_faithful() -> None:
    result = await _parse_corpus_file("synthetic_table_layout.docx")
    assert result.resume.contact.email == "sam.okafor@example.com"
    assert len(result.resume.experience) >= 1
    assert result.usage.input_tokens > 0
    # The DOCX is the clean fixture: bullets extract cleanly, so a faithful
    # transcription must pass the fuzzy-match check on every bullet.
    assert _drift_notes(result) == [], _drift_notes(result)
