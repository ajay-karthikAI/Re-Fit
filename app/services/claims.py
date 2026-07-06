"""Deterministic claim-diff checks for resume bullet rewrites.

This module is intentionally conservative. The LLM may suggest wording, but it
does not get to decide whether a rewrite preserved the source claims.
"""

from dataclasses import dataclass, field
import re

from rapidfuzz import fuzz

from app.schemas.jd import JobRequirements
from app.schemas.cover_letter import ProseClaimReport
from app.schemas.resume import ExperienceItem, StructuredResume

_NUMBER_RE = re.compile(
    r"""
    (?<![A-Za-z0-9])
    (
        \d{4}-\d{2}
        |
        \d+(?:,\d{3})*(?:\.\d+)?
        (?:\s?(?:%|[kKmMbB]|ms|s|rps|x|/day|/month))?
    )
    (?![A-Za-z0-9])
    """,
    re.VERBOSE,
)
_DATE_RE = re.compile(
    r"""
    \b(
        \d{4}-\d{2}
        |
        (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)
        [a-z]*\s+\d{4}
        |
        \d{4}
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
_CAPITALIZED_RE = re.compile(
    r"""
    \b
    (?:[A-Z][A-Za-z0-9+.#-]*|[A-Z0-9]{2,})
    \b
    """,
    re.VERBOSE,
)
_TERM_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.#-]*")

_GENERIC_TERM_TOKENS = {
    "ability",
    "another",
    "building",
    "clear",
    "communication",
    "comfort",
    "deep",
    "design",
    "experience",
    "expert",
    "expert-level",
    "familiarity",
    "general",
    "level",
    "minimum",
    "preferred",
    "prior",
    "production",
    "qualification",
    "qualifications",
    "required",
    "running",
    "services",
    "solid",
    "strong",
    "systems",
    "team",
    "tool",
    "tools",
    "written",
    "years",
}
_COMMON_SENTENCE_STARTERS = {
    "Architected",
    "Automated",
    "Built",
    "Collaborated",
    "Created",
    "Delivered",
    "Designed",
    "Developed",
    "Drove",
    "Enabled",
    "Enhanced",
    "Implemented",
    "Improved",
    "Led",
    "Maintained",
    "Managed",
    "Migrated",
    "Modernized",
    "Optimized",
    "Owned",
    "Partnered",
    "Reduced",
    "Refactored",
    "Shipped",
    "Supported",
    "Worked",
    "Wrote",
}
_PROSE_IGNORED_PROPER_NOUNS = {
    "Dear",
    "Hello",
    "Hi",
    "Sincerely",
    "Best",
    "Regards",
    "Thank",
    "Thanks",
    "I",
    "Your",
}
_PROSE_SENTENCE_START_FILLERS = {
    "Across",
    "After",
    "As",
    "At",
    "Because",
    "By",
    "For",
    "From",
    "In",
    "My",
    "That",
    "The",
    "These",
    "This",
    "Those",
    "Through",
    "When",
    "While",
    "With",
    "Your",
}
_COMPANY_FACT_STARTERS = {"your", "you", "the company", "this role", "the role"}


@dataclass(frozen=True)
class ExtractedClaims:
    numbers: set[str] = field(default_factory=set)
    capitalized_tokens: set[str] = field(default_factory=set)
    tech_terms: set[str] = field(default_factory=set)
    employer_title_strings: set[str] = field(default_factory=set)
    date_strings: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class ClaimVerificationResult:
    passed: bool
    reasons: list[str]
    original_claims: ExtractedClaims
    rewritten_claims: ExtractedClaims


def _normalize_number(value: str) -> str:
    return re.sub(r"\s+", "", value.replace(",", "")).lower()


def _normalize_term(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def _term_pattern(term: str) -> re.Pattern[str] | None:
    stripped = term.strip()
    if len(stripped) < 2:
        return None
    escaped = re.escape(stripped)
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


def _contains_term(text: str, term: str) -> bool:
    pattern = _term_pattern(term)
    return bool(pattern and pattern.search(text))


def _sentence_initial(text: str, start: int) -> bool:
    prefix = text[:start].rstrip()
    return not prefix or prefix[-1] in ".!?\n"


def _capitalized_occurrences(text: str) -> list[tuple[str, bool]]:
    occurrences: list[tuple[str, bool]] = []
    for match in _CAPITALIZED_RE.finditer(text):
        term = match.group(0)
        occurrences.append((term, _sentence_initial(text, match.start())))
    return occurrences


def _capitalized_tokens(text: str) -> set[str]:
    return {_normalize_term(term) for term, _ in _capitalized_occurrences(text)}


def _date_strings(text: str) -> set[str]:
    return {_normalize_term(match.group(1)) for match in _DATE_RE.finditer(text)}


def _number_strings(text: str) -> set[str]:
    return {_normalize_number(match.group(1)) for match in _NUMBER_RE.finditer(text)}


def _split_terms(value: str) -> set[str]:
    terms: set[str] = set()
    stripped = value.strip()
    if not stripped:
        return terms

    terms.add(stripped)
    for part in re.split(r"[/,;()|]+|\bor\b|\band\b", stripped, flags=re.IGNORECASE):
        part = part.strip(" -")
        if len(part) >= 2 and part.lower() not in _GENERIC_TERM_TOKENS:
            terms.add(part)

    for token in _TERM_TOKEN_RE.findall(stripped):
        if len(token) >= 2 and token.lower() not in _GENERIC_TERM_TOKENS:
            terms.add(token)

    return terms


def build_tech_lexicon(requirements: JobRequirements, profile: StructuredResume) -> set[str]:
    """Known skill/technology terms from the JD and the candidate profile."""
    terms: set[str] = set()

    for item in requirements.hard_skills:
        terms.update(_split_terms(item.term))
    for term in requirements.domain_terms:
        terms.update(_split_terms(term))
    for phrase in requirements.must_haves + requirements.nice_to_haves:
        for term, _ in _capitalized_occurrences(phrase):
            terms.update(_split_terms(term))

    for group in profile.skills:
        for item in group.items:
            terms.update(_split_terms(item))
    for item in profile.experience:
        for technology in item.technologies:
            terms.update(_split_terms(technology))
    for project in profile.projects:
        for technology in project.technologies:
            terms.update(_split_terms(technology))

    return {term for term in terms if len(term.strip()) >= 2}


def _tech_terms_in_text(text: str, lexicon: set[str]) -> set[str]:
    return {_normalize_term(term) for term in lexicon if _contains_term(text, term)}


def _protected_profile_strings(
    profile: StructuredResume, parent_experience: ExperienceItem | None
) -> set[str]:
    strings: set[str] = set()
    for item in profile.experience:
        strings.add(item.company)
        if len(item.title.strip()) > 1:
            strings.add(item.title)
        strings.add(item.start_date)
        if item.end_date is not None:
            strings.add(item.end_date)
    if parent_experience is not None:
        strings.update(
            {
                parent_experience.company,
                parent_experience.title,
                parent_experience.start_date,
            }
        )
        if parent_experience.end_date is not None:
            strings.add(parent_experience.end_date)
    return {value for value in strings if len(value.strip()) >= 2}


def _protected_strings_in_text(text: str, protected_strings: set[str]) -> set[str]:
    return {_normalize_term(term) for term in protected_strings if _contains_term(text, term)}


def extract_claims(
    text: str,
    *,
    tech_lexicon: set[str],
    protected_strings: set[str],
) -> ExtractedClaims:
    """Extract deterministic claim tokens from one bullet."""
    return ExtractedClaims(
        numbers=_number_strings(text),
        capitalized_tokens=_capitalized_tokens(text),
        tech_terms=_tech_terms_in_text(text, tech_lexicon),
        employer_title_strings=_protected_strings_in_text(text, protected_strings),
        date_strings=_date_strings(text),
    )


def _new_suspicious_capitalized_terms(
    *,
    original: str,
    rewritten: str,
    profile: StructuredResume,
    tech_lexicon: set[str],
    protected_strings: set[str],
) -> set[str]:
    original_caps = _capitalized_tokens(original)
    profile_text = profile.model_dump_json()
    profile_caps = _capitalized_tokens(profile_text)
    tech_terms = {_normalize_term(term) for term in tech_lexicon}
    protected_terms = {_normalize_term(term) for term in protected_strings}
    suspicious: set[str] = set()

    for term, is_sentence_initial in _capitalized_occurrences(rewritten):
        normalized = _normalize_term(term)
        plain_titlecase_word = bool(re.fullmatch(r"[A-Z][a-z]+", term))
        if is_sentence_initial and plain_titlecase_word and term not in _COMMON_SENTENCE_STARTERS:
            continue
        if term in _COMMON_SENTENCE_STARTERS:
            continue
        if (
            normalized in original_caps
            or normalized in profile_caps
            or normalized in tech_terms
            or normalized in protected_terms
        ):
            continue
        suspicious.add(term)

    return suspicious


def verify_rewrite(
    *,
    original: str,
    rewritten: str,
    profile: StructuredResume,
    requirements: JobRequirements,
    parent_experience: ExperienceItem | None = None,
) -> ClaimVerificationResult:
    """Return whether `rewritten` preserves the claims in `original`.

    A failing result means the caller must discard the rewrite and keep the
    original bullet.
    """
    tech_lexicon = build_tech_lexicon(requirements, profile)
    protected_strings = _protected_profile_strings(profile, parent_experience)
    original_claims = extract_claims(
        original, tech_lexicon=tech_lexicon, protected_strings=protected_strings
    )
    rewritten_claims = extract_claims(
        rewritten, tech_lexicon=tech_lexicon, protected_strings=protected_strings
    )
    reasons: list[str] = []

    introduced_numbers = sorted(rewritten_claims.numbers - original_claims.numbers)
    if introduced_numbers:
        reasons.append(f"introduced number(s): {', '.join(introduced_numbers)}")

    profile_text = profile.model_dump_json()
    original_tech = rewritten_claims.tech_terms & original_claims.tech_terms
    unbacked_tech = sorted(
        term
        for term in rewritten_claims.tech_terms - original_tech
        if not _contains_term(original, term) and not _contains_term(profile_text, term)
    )
    if unbacked_tech:
        reasons.append(f"introduced unbacked tech term(s): {', '.join(unbacked_tech)}")

    if original_claims.employer_title_strings != rewritten_claims.employer_title_strings:
        removed = sorted(
            original_claims.employer_title_strings - rewritten_claims.employer_title_strings
        )
        added = sorted(
            rewritten_claims.employer_title_strings - original_claims.employer_title_strings
        )
        details = []
        if removed:
            details.append(f"removed {', '.join(removed)}")
        if added:
            details.append(f"added {', '.join(added)}")
        reasons.append(f"changed employer/title/date string(s): {'; '.join(details)}")

    if original_claims.date_strings != rewritten_claims.date_strings:
        removed = sorted(original_claims.date_strings - rewritten_claims.date_strings)
        added = sorted(rewritten_claims.date_strings - original_claims.date_strings)
        details = []
        if removed:
            details.append(f"removed {', '.join(removed)}")
        if added:
            details.append(f"added {', '.join(added)}")
        reasons.append(f"changed date string(s): {'; '.join(details)}")

    introduced_caps = sorted(
        _new_suspicious_capitalized_terms(
            original=original,
            rewritten=rewritten,
            profile=profile,
            tech_lexicon=tech_lexicon,
            protected_strings=protected_strings,
        )
    )
    if introduced_caps:
        reasons.append(f"introduced unsupported capitalized claim(s): {', '.join(introduced_caps)}")

    return ClaimVerificationResult(
        passed=not reasons,
        reasons=reasons,
        original_claims=original_claims,
        rewritten_claims=rewritten_claims,
    )


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    return [
        sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", normalized) if sentence.strip()
    ]


def _proper_noun_phrases(text: str) -> set[str]:
    phrases: set[str] = set()
    pattern = re.compile(
        r"""
        (?<![A-Za-z0-9])
        (
            (?:[A-Z][A-Za-z0-9+#-]*(?:\.[A-Za-z0-9+#-]+)*|[A-Z][A-Z0-9]{1,})
            (?:[ \t]+(?:[A-Z][A-Za-z0-9+#-]*(?:\.[A-Za-z0-9+#-]+)*|[A-Z][A-Z0-9]{1,}))*
        )
        """,
        re.VERBOSE,
    )
    for match in pattern.finditer(text):
        phrase = match.group(1).strip()
        if not phrase:
            continue
        phrase = re.sub(r"\b([A-Z][A-Za-z0-9+#.]*)-[a-z][A-Za-z0-9-]*\b", r"\1", phrase)
        words = phrase.split()
        if (
            _sentence_initial(text, match.start())
            and len(words) > 1
            and words[0] in _PROSE_SENTENCE_START_FILLERS | _PROSE_IGNORED_PROPER_NOUNS
        ):
            phrase = " ".join(words[1:])
            words = phrase.split()
            if not phrase:
                continue
        if all(word in _PROSE_IGNORED_PROPER_NOUNS for word in words):
            continue
        if len(words) == 1:
            word = words[0]
            if word in _PROSE_IGNORED_PROPER_NOUNS:
                continue
            if _sentence_initial(text, match.start()) and re.fullmatch(r"[A-Z][a-z]+", word):
                continue
            if _sentence_initial(text, match.start()) and word in _PROSE_SENTENCE_START_FILLERS:
                continue
            if word in _COMMON_SENTENCE_STARTERS and _sentence_initial(text, match.start()):
                continue
        phrases.add(phrase)
    return phrases


def _supported_by_sources(term: str, sources: list[str], *, threshold: int = 90) -> bool:
    normalized = _normalize_term(term)
    if not normalized:
        return True
    for source in sources:
        source_normalized = _normalize_term(source)
        if normalized in source_normalized:
            return True
        if fuzz.partial_ratio(normalized, source_normalized) >= threshold:
            return True
    parts = [part for part in re.split(r"\s+", term.strip()) if len(part) > 1]
    if len(parts) > 1:
        return all(_supported_by_sources(part, sources, threshold=threshold) for part in parts)
    return False


def _company_name_candidates(raw_jd: str, profile: StructuredResume) -> set[str]:
    del profile
    candidates: set[str] = set()
    for pattern in [
        r"(?im)^[^\n—-]+\s+[—-]\s+([A-Z][^\n(,;]+)",
        r"(?im)^\s*company\s*:\s*([A-Z][^\n,.;]+)",
        r"(?im)^\s*about\s+([A-Z][A-Za-z0-9& .'-]+)\s*$",
    ]:
        for match in re.finditer(pattern, raw_jd):
            candidate = match.group(1).strip()
            if candidate.lower() not in {"us", "the role", "the company"}:
                candidates.add(candidate)
    return {
        candidate for candidate in candidates if len(candidate) >= 3 and len(candidate.split()) >= 2
    }


def _is_company_fact_sentence(sentence: str, company_names: set[str]) -> bool:
    normalized = _normalize_term(sentence)
    if any(normalized.startswith(starter) for starter in _COMPANY_FACT_STARTERS):
        return True
    return any(normalized.startswith(_normalize_term(name)) for name in company_names)


def _company_fact_clause(sentence: str) -> str:
    return re.split(
        r"(?:,\s+and\s+|\s+and\s+)(?:I|my|the profile|the resume)\b",
        sentence,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()


def verify_prose(body: str, profile: StructuredResume, raw_jd: str) -> ProseClaimReport:
    """Verify generated prose against candidate profile and JD sources.

    The check is intentionally conservative: proper nouns and numbers in prose
    must be visible in the profile or JD, and company-facing sentences must
    overlap with an actual JD sentence.
    """

    profile_text = profile.model_dump_json()
    sources = [profile_text, raw_jd]
    violations: list[str] = []

    proper_nouns = sorted(_proper_noun_phrases(body))
    for term in proper_nouns:
        if not _supported_by_sources(term, sources):
            violations.append(f"unsupported proper noun: {term}")

    numbers = sorted(_number_strings(body))
    source_numbers = _number_strings(profile_text) | _number_strings(raw_jd)
    for number in numbers:
        if number not in source_numbers:
            violations.append(f"unsupported number: {number}")

    jd_sentences = _split_sentences(raw_jd)
    jd_sentences.extend(
        line.strip(" -") for line in raw_jd.splitlines() if len(line.strip(" -")) >= 10
    )
    company_names = _company_name_candidates(raw_jd, profile)
    company_fact_sentences = [
        sentence
        for sentence in _split_sentences(body)
        if _is_company_fact_sentence(sentence, company_names)
    ]
    for sentence in company_fact_sentences:
        clause = _company_fact_clause(sentence)
        best_overlap = max(
            (
                fuzz.partial_ratio(_normalize_term(clause), _normalize_term(jd_sentence))
                for jd_sentence in jd_sentences
            ),
            default=0,
        )
        if best_overlap < 60:
            violations.append(f"company fact not grounded in JD: {sentence}")

    return ProseClaimReport(
        passed=not violations,
        violations=violations,
        proper_nouns_checked=proper_nouns,
        numbers_checked=numbers,
        company_fact_sentences_checked=company_fact_sentences,
    )
