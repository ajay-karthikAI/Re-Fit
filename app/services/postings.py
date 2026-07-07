"""Storage + dedup layer for ingested job postings.

This is what keeps ingestion honest across runs: the same posting is re-fetched
every cycle, so we upsert by ``(source_board_id, external_id)`` instead of
piling up rows, detect real content changes via a hash, soft-expire postings
that drop out of a fetch, and link (never merge) the same role syndicated across
two different boards.

Two dedup passes, deliberately different in confidence:

1. **Primary, exact:** ``(source_board_id, external_id)`` uniqueness. This is
   authoritative — the source's own id within its board.
2. **Secondary, fuzzy, cross-board:** normalized ``company + title`` compared
   with rapidfuzz. Biased hard toward *under*-merging: a missed link just leaves
   one duplicate in a digest; a wrong link would hide a genuinely distinct
   opening. Matches are linked via ``canonical_posting_id`` with both rows kept.
"""

import hashlib
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.posting import Posting
from app.models.source_board import SourceBoard
from app.schemas.postings import IngestResult
from app.schemas.sources import RawPosting

logger = logging.getLogger(__name__)


def _normalize(value: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace — for hashing and for
    the fuzzy cross-board key."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value).strip().lower())


def content_hash(title: str, description_text: str) -> str:
    """Stable hash of the fields that matter for change detection."""
    payload = f"{_normalize(title)}\x1f{_normalize(description_text)}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _dedup_key(company_name: str, title: str) -> str:
    return _normalize(f"{company_name} {title}")


async def upsert_postings(
    session: AsyncSession, board: SourceBoard, raw_postings: list[RawPosting]
) -> IngestResult:
    """Upsert one board's fetch into the postings table and return the tally.

    For each raw posting: upsert by ``(source_board_id, external_id)``, refresh
    ``last_seen_at``, and recompute ``content_hash``. An unchanged hash on an
    already-active row is ``unchanged``; a changed hash — or reactivating a row
    that had been deactivated — is ``updated`` (re-triggers scoring later). Rows
    active on this board but absent from this fetch are soft-deactivated.
    """
    now = datetime.now(UTC)
    result = IngestResult()

    existing = {
        p.external_id: p
        for p in (await session.execute(select(Posting).where(Posting.source_board_id == board.id)))
        .scalars()
        .all()
    }
    seen: set[str] = set()

    for raw in raw_postings:
        seen.add(raw.external_id)
        new_hash = content_hash(raw.title, raw.description_text)
        posting = existing.get(raw.external_id)

        if posting is None:
            session.add(
                Posting(
                    source_board_id=board.id,
                    external_id=raw.external_id,
                    title=raw.title,
                    location=raw.location,
                    department=raw.department,
                    url=raw.url,
                    description_text=raw.description_text,
                    posted_at=raw.posted_at,
                    content_hash=new_hash,
                    first_seen_at=now,
                    last_seen_at=now,
                    is_active=True,
                )
            )
            result.created += 1
            continue

        posting.last_seen_at = now
        reactivated = not posting.is_active
        content_changed = posting.content_hash != new_hash

        if content_changed:
            posting.title = raw.title
            posting.location = raw.location
            posting.department = raw.department
            posting.url = raw.url
            posting.description_text = raw.description_text
            posting.posted_at = raw.posted_at
            posting.content_hash = new_hash
            # The cached JD requirements were extracted from the old text.
            posting.extracted_requirements = None
        if reactivated:
            posting.is_active = True
            posting.deactivated_at = None

        if content_changed or reactivated:
            result.updated += 1
        else:
            result.unchanged += 1

    for external_id, posting in existing.items():
        if external_id not in seen and posting.is_active:
            posting.is_active = False
            posting.deactivated_at = now
            result.deactivated += 1

    await session.commit()

    await link_cross_board_duplicates(session, board)
    return result


async def link_cross_board_duplicates(session: AsyncSession, board: SourceBoard) -> int:
    """Link this board's active postings to matching ones on *other* boards.

    Compares normalized company+title with rapidfuzz. On a match above the
    configured threshold, the newer posting (this board's) is pointed at the
    older posting's canonical row via ``canonical_posting_id`` — both rows are
    kept; only the canonical is later surfaced in the digest. Returns the number
    of new links created. Never merges or deletes.
    """
    settings = get_settings()
    threshold = settings.crossboard_dedup_threshold

    # Candidates: active postings on other boards, with their board's company.
    candidate_rows = (
        await session.execute(
            select(Posting, SourceBoard.company_name)
            .join(SourceBoard, Posting.source_board_id == SourceBoard.id)
            .where(Posting.is_active.is_(True), Posting.source_board_id != board.id)
        )
    ).all()
    candidates = [
        (posting, _dedup_key(company_name, posting.title))
        for posting, company_name in candidate_rows
    ]

    mine = (
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

    links = 0
    for posting in mine:
        key = _dedup_key(board.company_name, posting.title)
        best: Posting | None = None
        best_score = threshold
        for candidate, candidate_key in candidates:
            if candidate.id == posting.id:
                continue
            score = fuzz.token_sort_ratio(key, candidate_key)
            if score >= best_score:
                best_score = score
                best = candidate

        if best is None:
            continue

        # Point at the candidate's canonical row (or the candidate itself if it
        # is canonical), so the canonical stays stable and links never chain.
        canonical_id = best.canonical_posting_id or best.id
        if canonical_id == posting.id:
            continue  # never point a row at itself
        posting.canonical_posting_id = canonical_id
        links += 1
        logger.info(
            "cross-board dedup: linked posting %s (board %s, %r) -> canonical %s [score=%.1f]",
            posting.id,
            board.id,
            posting.title,
            canonical_id,
            best_score,
        )

    if links:
        await session.commit()
    return links


async def deactivate_stale_postings(session: AsyncSession) -> int:
    """Freshness sweep: deactivate any still-active posting whose ``last_seen_at``
    is older than the configured window.

    Catches postings orphaned by boards that stopped being fetched (e.g. went
    dead) or boards that never remove their own stale listings. Returns the
    number deactivated.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=settings.posting_freshness_days)

    stale = (
        (
            await session.execute(
                select(Posting).where(Posting.is_active.is_(True), Posting.last_seen_at < cutoff)
            )
        )
        .scalars()
        .all()
    )
    for posting in stale:
        posting.is_active = False
        posting.deactivated_at = now

    if stale:
        await session.commit()
    return len(stale)


async def get_posting(session: AsyncSession, posting_id: uuid.UUID) -> Posting | None:
    return await session.get(Posting, posting_id)
