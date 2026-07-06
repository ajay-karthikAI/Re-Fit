"""JD requirement extraction: raw job description text -> JobRequirements.

One structured-output call through app/services/llm.py.
"""

import logging

from app.schemas.jd import JobRequirements
from app.schemas.llm import LLMUsage
from app.services.llm import generate_structured

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
"""


async def extract_requirements(
    raw_jd: str, model: str | None = None
) -> tuple[JobRequirements, LLMUsage]:
    requirements, usage = await generate_structured(
        JobRequirements,
        system=SYSTEM_PROMPT,
        user_content=f"Job description:\n\n{raw_jd}",
        model=model,
    )
    return requirements, usage
