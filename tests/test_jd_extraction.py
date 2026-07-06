"""JD requirement-extraction integration tests against the real OpenAI API.

Skipped without a usable OPENAI_API_KEY. Runs over every .txt in
tests/corpus/jds/ (synthetic placeholders now; real JDs as they land).
"""

import os
from pathlib import Path

import pytest

from app.config import get_settings
from app.services.jd import extract_requirements

CORPUS_JDS = Path(__file__).parent / "corpus" / "jds"
_PLACEHOLDER_KEYS = {"", "changeme"}

SENIORITY_VALUES = {"intern", "junior", "mid", "senior", "staff", "lead", "unknown"}


def _api_key_available() -> bool:
    env_key = os.environ.get("OPENAI_API_KEY", "")
    settings_key = get_settings().openai_api_key
    return env_key not in _PLACEHOLDER_KEYS or settings_key not in _PLACEHOLDER_KEYS


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _api_key_available(), reason="OPENAI_API_KEY is unset"),
]


def _jd_files() -> list[Path]:
    return sorted(CORPUS_JDS.glob("*.txt"))


@pytest.mark.parametrize("path", _jd_files(), ids=lambda p: p.name)
async def test_extract_requirements_from_corpus_jd(path: Path) -> None:
    requirements, usage = await extract_requirements(path.read_text())

    assert requirements.seniority in SENIORITY_VALUES
    assert len(requirements.hard_skills) >= 3
    for item in requirements.hard_skills + requirements.soft_skills:
        assert 0.0 <= item.weight <= 1.0
        assert item.evidence.strip()
    assert usage.input_tokens > 0
    assert usage.output_tokens > 0
