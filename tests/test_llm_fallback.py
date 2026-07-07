"""The explicit, opt-in heuristic fallback for JD extraction.

The test env has a placeholder OPENAI_API_KEY (``changeme`` from .env.example),
so these exercise the key-less branch directly — no network, no real LLM.
"""

import pytest

from app.services.jd import extract_requirements, extract_requirements_heuristic
from app.services.llm import MissingLLMCredentialsError, is_placeholder_key

_JD = (
    "We are hiring a Senior Machine Learning Engineer. You will build NLP and LLM "
    "systems in Python with PyTorch, deploy on Kubernetes and AWS. SQL required."
)


def test_placeholder_key_detection() -> None:
    assert is_placeholder_key("") is True
    assert is_placeholder_key(None) is True
    assert is_placeholder_key("changeme") is True
    assert is_placeholder_key("change-this-key") is True
    assert is_placeholder_key("sk-reallookingkey123") is False


async def test_refuses_heuristic_when_not_opted_in_even_with_placeholder_key() -> None:
    # Default heuristic_fallback=False + placeholder key -> typed refusal, not a
    # silent downgrade.
    with pytest.raises(MissingLLMCredentialsError):
        await extract_requirements(_JD)


async def test_opt_in_heuristic_returns_tagged_output() -> None:
    requirements, usage = await extract_requirements(_JD, heuristic_fallback=True)

    assert requirements.source == "heuristic"
    assert usage.input_tokens == 0 and usage.output_tokens == 0  # no LLM call
    terms = {item.term for item in requirements.hard_skills}
    assert {"Python", "PyTorch", "Kubernetes", "AWS", "SQL"} <= terms
    # Every evidence string is clearly marked as an approximation.
    assert requirements.hard_skills, "expected some hard skills"
    assert all(item.evidence.startswith("[heuristic]") for item in requirements.hard_skills)
    assert requirements.seniority == "senior"


def test_heuristic_function_is_deterministic_and_tagged() -> None:
    a = extract_requirements_heuristic(_JD)
    b = extract_requirements_heuristic(_JD)
    assert a.source == "heuristic"
    assert [i.term for i in a.hard_skills] == [i.term for i in b.hard_skills]
    # must_haves are drawn from found terms, also approximation-derived.
    assert a.must_haves and all(m in {i.term for i in a.hard_skills} for m in a.must_haves)


def test_empty_jd_heuristic_is_empty_but_valid() -> None:
    result = extract_requirements_heuristic("")
    assert result.source == "heuristic"
    assert result.hard_skills == []
    assert result.seniority == "unknown"
