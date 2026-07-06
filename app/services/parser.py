"""LLM normalization: raw extracted resume text → StructuredResume.

One structured-output call through app/services/llm.py, followed by a
deterministic faithfulness check (rapidfuzz) that flags bullets which don't
fuzzy-match the raw text as possible paraphrase drift.
"""

import logging

from rapidfuzz import fuzz

from app.schemas.extract import ExtractedText
from app.schemas.parse import ParseResult, ResumeParseOutput
from app.schemas.resume import StructuredResume
from app.services.llm import generate_structured

logger = logging.getLogger(__name__)

FAITHFULNESS_THRESHOLD = 85
"""Minimum rapidfuzz partial_ratio for a bullet against the raw text."""

SYSTEM_PROMPT = """\
You transcribe resumes from raw extracted text into a strict JSON schema.

Rules — these are product invariants, not suggestions:

1. TRANSCRIBE, DON'T IMPROVE. Preserve the candidate's wording in bullets
   verbatim wherever possible. You may fix only encoding artifacts, stray
   spacing from PDF extraction (e.g. "J ORDAN" -> "JORDAN"), and broken line
   wraps. Never rephrase, strengthen, or embellish.

2. NEVER INVENT DATA. If a field is not present in the text, leave it null or
   empty — do not guess emails, dates, locations, technologies, or anything
   else. Include dates only when explicitly present; convert formats like
   "Jan 2023" to "2023-01". If only a year is given with no month, omit the
   date and record that in confidence_notes. A missing end date on a current
   role is null (meaning "present").

3. UNRECOGNIZED SECTIONS (certifications, publications, awards, volunteering,
   ...) go into projects or education details, whichever fits better. Record
   each such placement decision in confidence_notes.

4. The text may come from imperfect extraction of multi-column layouts, so
   related pieces (a job title and its dates) may appear out of order —
   reassemble them carefully, but only using what is actually in the text.

Use confidence_notes for anything you were unsure about.
"""


def _faithfulness_notes(resume: StructuredResume, raw_text: str) -> list[str]:
    """Deterministic post-LLM check: every experience bullet must fuzzy-match
    the raw text. Failures are warnings (noted + logged), not hard errors."""
    notes: list[str] = []
    haystack = raw_text.lower()
    for item in resume.experience:
        for bullet in item.bullets:
            score = fuzz.partial_ratio(bullet.lower(), haystack)
            if score < FAITHFULNESS_THRESHOLD:
                note = (
                    f"possible paraphrase drift ({item.company}): "
                    f'"{bullet}" (match score {score:.0f} < {FAITHFULNESS_THRESHOLD})'
                )
                logger.warning("faithfulness check failed: %s", note)
                notes.append(note)
    return notes


def _to_domain(output: ResumeParseOutput) -> tuple[StructuredResume, list[str]]:
    """Enforce the real schema (dates, email/URL formats, bullet lengths).

    Raising here re-enters generate_structured's retry loop with the
    validation error fed back to the model.
    """
    resume = StructuredResume.model_validate(output.resume.model_dump())
    return resume, output.confidence_notes


async def parse_resume(extracted: ExtractedText, model: str | None = None) -> ParseResult:
    user_content = (
        f"Raw resume text (extracted from a {extracted.source_format.upper()} file"
        + (
            f"; extraction warnings: {'; '.join(extracted.extraction_warnings)}"
            if extracted.extraction_warnings
            else ""
        )
        + f"):\n\n{extracted.raw_text}"
    )

    (resume, llm_notes), usage = await generate_structured(
        ResumeParseOutput,
        system=SYSTEM_PROMPT,
        user_content=user_content,
        model=model,
        validate_extra=_to_domain,
    )

    notes = list(llm_notes)
    notes.extend(_faithfulness_notes(resume, extracted.raw_text))
    return ParseResult(resume=resume, confidence_notes=notes, usage=usage)
