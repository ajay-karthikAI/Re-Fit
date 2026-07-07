"""JD requirement extraction: raw job description text -> JobRequirements.

The real path is one structured-output call through app/services/llm.py (the
single LLM gateway, per CLAUDE.md). A separate, clearly-labelled heuristic
keyword extractor exists as an *explicit, opt-in* fallback for environments with
no real LLM key — it is never reached silently: a caller must pass
``heuristic_fallback=True`` AND the configured key must be placeholder-shaped.
Any real-key failure (timeout, rate limit, validation) still flows through the
gateway's retry-then-typed-error path.
"""

import logging

from app.config import get_settings
from app.schemas.jd import JobRequirements, RequirementItem
from app.schemas.llm import LLMUsage
from app.services.llm import (
    MissingLLMCredentialsError,
    generate_structured,
    is_placeholder_key,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You extract structured hiring requirements from raw job descriptions.

Rules:

1. NEVER INVENT REQUIREMENTS. Every extracted item must be grounded in the JD
   text. The `evidence` field of each requirement must be a short verbatim
   snippet (a phrase or clause, not a whole paragraph) copied from the JD.

2. WEIGHTS reflect emphasis in the JD, on a 0-1 scale: requirements that are
   repeated, listed first, or marked as required/essential get higher weights;
   passing mentions get lower weights. Use the full range, not just 1.0.

3. hard_skills are concrete technologies, languages, tools, and techniques.
   soft_skills are behavioral/collaborative expectations. domain_terms are
   industry or product vocabulary worth mirroring in a resume (e.g.
   "observability", "HIPAA", "real-time bidding") that are not skills per se.

4. must_haves are requirements the JD explicitly marks as required
   ("must have", "required", "minimum qualifications"). nice_to_haves are
   explicitly optional ("nice to have", "preferred", "bonus"). Keep these as
   short plain-text phrases.

5. seniority comes from the title and leveling cues (years of experience,
   scope of ownership). Use "unknown" when the JD genuinely doesn't say —
   do not guess.

6. Set `source` to "llm".
"""

# Vocabulary the heuristic fallback can recognize by surface form. Kept small and
# obvious on purpose — this path is an approximation, not a competitor to the LLM.
_HEURISTIC_VOCAB: tuple[str, ...] = (
    "Python",
    "Java",
    "JavaScript",
    "TypeScript",
    "Go",
    "Rust",
    "C++",
    "C#",
    "Scala",
    "Ruby",
    "SQL",
    "React",
    "Node.js",
    "FastAPI",
    "Django",
    "Flask",
    "Spring",
    "PyTorch",
    "TensorFlow",
    "scikit-learn",
    "Hugging Face",
    "Kubernetes",
    "Docker",
    "AWS",
    "GCP",
    "Azure",
    "Terraform",
    "Kafka",
    "Airflow",
    "Spark",
    "Snowflake",
    "Postgres",
    "PostgreSQL",
    "Redis",
    "MongoDB",
    "GraphQL",
    "REST",
    "gRPC",
    "machine learning",
    "deep learning",
    "NLP",
    "LLM",
    "computer vision",
    "MLOps",
    "data engineering",
    "distributed systems",
    "microservices",
    "CI/CD",
    "observability",
    "HIPAA",
    "pathology",
    "clinical",
    "healthcare",
)

_SENIORITY_CUES: tuple[tuple[str, str], ...] = (
    ("intern", "intern"),
    ("staff", "staff"),
    ("principal", "lead"),
    ("lead ", "lead"),
    ("senior", "senior"),
    ("sr.", "senior"),
    ("junior", "junior"),
    ("entry level", "junior"),
)


async def extract_requirements(
    raw_jd: str,
    model: str | None = None,
    *,
    heuristic_fallback: bool = False,
) -> tuple[JobRequirements, LLMUsage]:
    """Extract requirements from a JD via the LLM gateway.

    With a real key configured, always uses the LLM (``heuristic_fallback`` is
    irrelevant). With a placeholder-shaped key: raises
    ``MissingLLMCredentialsError`` unless the caller explicitly opts into the
    approximation with ``heuristic_fallback=True``. Real-key failures are never
    downgraded — they propagate from the gateway.
    """
    key = get_settings().openai_api_key
    if is_placeholder_key(key):
        if not heuristic_fallback:
            raise MissingLLMCredentialsError(
                "OPENAI_API_KEY is missing or a placeholder; refusing to extract "
                "requirements. Pass heuristic_fallback=True to opt into the "
                "clearly-labelled approximation, or configure a real key."
            )
        logger.warning(
            "extract_requirements: NO REAL LLM KEY — using explicit heuristic "
            "keyword fallback (source='heuristic', approximate)."
        )
        return extract_requirements_heuristic(raw_jd), LLMUsage()

    requirements, usage = await generate_structured(
        JobRequirements,
        system=SYSTEM_PROMPT,
        user_content=f"Job description:\n\n{raw_jd}",
        model=model,
    )
    # Authoritative regardless of what the model emitted for the field.
    return requirements.model_copy(update={"source": "llm"}), usage


def extract_requirements_heuristic(raw_jd: str) -> JobRequirements:
    """Deterministic keyword-matching approximation of JD extraction.

    Same ``JobRequirements`` shape as the LLM path, but every ``evidence`` string
    is prefixed ``[heuristic]`` and ``source`` is ``"heuristic"`` so downstream
    consumers and eval reports can never mistake it for a real extraction. This
    is a labelled approximation, not a scorer of record.
    """
    lowered = raw_jd.lower()
    found: list[str] = []
    for term in _HEURISTIC_VOCAB:
        if term.lower() in lowered and term not in found:
            found.append(term)

    hard_skills = [
        RequirementItem(
            term=term,
            weight=0.7,
            evidence=f"[heuristic] surface term '{term}' present in description",
        )
        for term in found
    ]

    seniority = "unknown"
    for cue, level in _SENIORITY_CUES:
        if cue in lowered:
            seniority = level
            break

    return JobRequirements(
        hard_skills=hard_skills,
        soft_skills=[],
        domain_terms=[],
        seniority=seniority,  # type: ignore[arg-type]
        must_haves=found[:3],
        nice_to_haves=[],
        source="heuristic",
    )
