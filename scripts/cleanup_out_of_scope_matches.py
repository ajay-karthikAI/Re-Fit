"""One-off cleanup: delete ``posting_matches`` rows that violate the ownership
invariant.

Before the ownership scope was enforced, ``refresh_matches_for_search`` scored
every active canonical posting against every saved search regardless of which
boards the search's owner actually watches. That could persist
``posting_matches`` rows whose posting lives on a board owned by a *different*
user — outside the search owner's visibility scope.

A row is out of scope iff its posting's ``source_board`` is owned by some user
who is **not** the saved search's owner (system/seed boards, ``user_id IS
NULL``, are in scope for everyone and are never deleted here). This is the
negation of ``matching.visible_board_condition``.

This is intentionally a **script, not a migration**: it repairs data written by
old runs and is safe to re-run (idempotent — a clean database deletes nothing).
Read-time queries already AND in the ownership predicate, so this is belt-and-
suspenders that also keeps the cache honest.

Run with: uv run python -m scripts.cleanup_out_of_scope_matches
Pass --dry-run to report the count without deleting.
"""

import argparse
import asyncio

from sqlalchemy import delete, func, select

from app.db import dispose_engine, get_session_factory
from app.models import Posting, PostingMatch, SavedSearch, SourceBoard


def _out_of_scope_match_ids():
    """SELECT of ``posting_matches.id`` whose posting's board is neither the
    saved search owner's nor a system/seed board."""
    return (
        select(PostingMatch.id)
        .join(SavedSearch, PostingMatch.saved_search_id == SavedSearch.id)
        .join(Posting, PostingMatch.posting_id == Posting.id)
        .join(SourceBoard, Posting.source_board_id == SourceBoard.id)
        .where(
            SourceBoard.user_id.is_not(None),
            SourceBoard.user_id != SavedSearch.user_id,
        )
    )


async def main(*, dry_run: bool = False) -> int:
    factory = get_session_factory()
    async with factory() as session:
        ids_subq = _out_of_scope_match_ids().subquery()
        count = (
            await session.execute(select(func.count()).select_from(ids_subq))
        ).scalar_one()

        if dry_run:
            print(f"[dry-run] {count} out-of-scope posting_matches row(s) would be deleted")
            await dispose_engine()
            return count

        await session.execute(
            delete(PostingMatch).where(PostingMatch.id.in_(select(ids_subq.c.id)))
        )
        await session.commit()
        print(f"deleted {count} out-of-scope posting_matches row(s)")
    await dispose_engine()
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many rows are out of scope without deleting them.",
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
