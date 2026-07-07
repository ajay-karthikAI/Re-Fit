"use client";

import { useQuery } from "@tanstack/react-query";

import { type SavedSearch, listMatches } from "@/lib/api";
import { DigestHistory } from "@/components/job-feed/digest-history";
import { MatchFilter } from "@/components/job-feed/match-filter";
import { PostingCard } from "@/components/job-feed/posting-card";

export function SavedSearchFeed({
  search,
  userId
}: {
  search: SavedSearch;
  userId: string;
}) {
  const query = useQuery({
    queryKey: ["matches", search.id],
    queryFn: () => listMatches(search.id)
  });

  const matches = query.data ?? [];

  return (
    <div className="space-y-8">
      {query.isLoading ? (
        <p className="text-sm text-subdued">Loading matches…</p>
      ) : matches.length === 0 ? (
        <div className="rounded-xl border border-border bg-muted p-8">
          <h2 className="text-lg font-semibold text-text">No matches yet</h2>
          <p className="mt-1 text-sm text-subdued">
            Postings scoring at or above this search&apos;s bar will appear here after the next
            ingestion + scoring run.
          </p>
        </div>
      ) : (
        <MatchFilter matches={matches} initialMinScore={search.min_score}>
          {(filtered) =>
            filtered.length === 0 ? (
              <p className="text-sm text-subdued">
                No matches at this score. Lower the bar to see more.
              </p>
            ) : (
              <ul className="space-y-3" data-testid="posting-list">
                {filtered.map((match) => (
                  <PostingCard key={match.posting_id} match={match} userId={userId} />
                ))}
              </ul>
            )
          }
        </MatchFilter>
      )}

      <DigestHistory savedSearchId={search.id} />
    </div>
  );
}
