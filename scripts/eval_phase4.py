"""Phase 4 matching eval: score real ingested postings against a profile.

This is the one eval whose only LLM call is JD requirement extraction, so it can
run end-to-end in heuristic mode. The guardrail refuses a placeholder key unless
--allow-heuristic. The heuristic decision lives HERE, in the caller: this script
pre-populates each posting's requirements via
``extract_requirements(..., heuristic_fallback=heuristic_mode)`` and then lets
``matching`` consume the cache — the matching service never opts into the
heuristic itself. The report header and every row are tagged with the source.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path
import uuid

from sqlalchemy import delete, select

from app.db import dispose_engine, get_session_factory
from app.models import Posting, Profile, SavedSearch, SourceBoard, User
from app.models.source_board import SourceKind
from app.schemas.resume import StructuredResume
from app.services.jd import extract_requirements
from app.services.matching import refresh_matches_for_search
from app.services.postings import upsert_postings
from app.services.sources import registry
from scripts._llm_guard import HEURISTIC_REPORT_HEADER, guard_llm_or_exit

REPORT_DIR = Path("eval_reports")
_EMAIL = "eval-phase4@example.com"

_PROFILE = StructuredResume(
    contact={"full_name": "Eval Profile", "email": "eval@example.com"},
    summary="Machine learning engineer: NLP, LLMs, and ML platform work.",
    experience=[
        {
            "company": "Nimbus AI",
            "title": "Senior Machine Learning Engineer",
            "start_date": "2021-03",
            "end_date": None,
            "bullets": [
                "Built NLP and LLM services in Python with PyTorch on AWS.",
                "Owned training pipelines with Docker and Kubernetes.",
            ],
            "technologies": ["Python", "PyTorch", "AWS", "Kubernetes"],
        }
    ],
    education=[{"institution": "State U", "degree": "BS", "field": "CS"}],
    skills=[{"category": "ML", "items": ["PyTorch", "NLP", "LLMs", "machine learning"]}],
    projects=[],
)


async def _run(board_token: str, company: str, heuristic_mode: bool, limit: int | None) -> Path:
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(delete(User).where(User.email == _EMAIL))
        await session.execute(delete(SourceBoard).where(SourceBoard.identifier == board_token))
        await session.commit()

        user = User(email=_EMAIL)
        session.add(user)
        await session.commit()
        profile = Profile(user_id=user.id, data=_PROFILE.model_dump(mode="json"))
        session.add(profile)
        await session.commit()
        board = SourceBoard(
            source=SourceKind.greenhouse, identifier=board_token, company_name=company
        )
        session.add(board)
        await session.commit()
        search = SavedSearch(
            user_id=user.id, name="Phase 4 eval", profile_id=profile.id, min_score=0.0
        )
        session.add(search)
        await session.commit()

        raws = await registry.fetch_board(session, board)
        await upsert_postings(session, board, raws)

        # Seed requirements on EVERY active canonical posting matching will score
        # — not a subset. Leaving any unseeded would (correctly) make matching
        # raise MissingLLMCredentialsError rather than silently degrade.
        postings = (
            (
                await session.execute(
                    select(Posting).where(
                        Posting.source_board_id == board.id,
                        Posting.is_active.is_(True),
                        Posting.canonical_posting_id.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )

        # Caller-owned decision: extract (real or heuristic) and cache on the posting.
        for posting in postings:
            requirements, _ = await extract_requirements(
                posting.description_text, heuristic_fallback=heuristic_mode
            )
            posting.extracted_requirements = requirements.model_dump(mode="json")
        await session.commit()

        await refresh_matches_for_search(session, search)

        report_path = await _write_report(
            session, search.id, company, heuristic_mode, len(postings), limit
        )

        await session.execute(delete(User).where(User.id == user.id))
        await session.execute(delete(SourceBoard).where(SourceBoard.id == board.id))
        await session.commit()
        return report_path


async def _write_report(
    session,
    search_id: uuid.UUID,
    company: str,
    heuristic_mode: bool,
    scored: int,
    limit: int | None,
) -> Path:
    from app.models import PostingMatch

    rows = (
        await session.execute(
            select(PostingMatch, Posting)
            .join(Posting, PostingMatch.posting_id == Posting.id)
            .where(PostingMatch.saved_search_id == search_id)
            .order_by(PostingMatch.score.desc())
        )
    ).all()
    if limit is not None:
        rows = rows[:limit]

    sources = {(p.extracted_requirements or {}).get("source", "?") for _, p in rows}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = REPORT_DIR / f"phase4_{timestamp}.md"

    body = [
        "# Phase 4 Matching Eval",
        "",
        *([HEURISTIC_REPORT_HEADER, ""] if heuristic_mode else []),
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "## Summary",
        "",
        f"- Company/board: {company}",
        f"- Postings scored: {scored}",
        f"- Requirement source(s): {', '.join(sorted(sources))}",
        "",
        "## Ranked matches",
        "",
        "| score | source | title | missing (top 5) |",
        "|------:|--------|-------|-----------------|",
    ]
    for match, posting in rows:
        source = (posting.extracted_requirements or {}).get("source", "?")
        missing = ", ".join(match.missing_terms[:5]) or "—"
        title = posting.title.replace("|", "/")
        body.append(f"| {match.score:.1f} | {source} | {title} | {missing} |")
    body.append("")

    path.write_text("\n".join(body))
    return path


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", default="pathai", help="Greenhouse board token.")
    parser.add_argument("--company", default="PathAI")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--allow-heuristic",
        action="store_true",
        help="Permit running with NO real LLM key, using the heuristic approximation.",
    )
    args = parser.parse_args()

    heuristic_mode = guard_llm_or_exit(args.allow_heuristic, "eval_phase4")

    try:
        path = await _run(args.board, args.company, heuristic_mode, args.limit)
    finally:
        await dispose_engine()
    print(f"wrote {path}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
