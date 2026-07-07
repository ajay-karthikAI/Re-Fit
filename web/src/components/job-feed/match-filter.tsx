"use client";

import { type ReactNode, useState } from "react";

import type { PostingMatch } from "@/lib/api";
import { MinScoreSlider } from "@/components/job-feed/min-score-slider";

/** Pure narrowing of the matches query by score — extracted so it is testable. */
export function filterMatchesByScore(matches: PostingMatch[], minScore: number): PostingMatch[] {
  return matches.filter((match) => match.score >= minScore);
}

/**
 * Live score filter over a saved search's matches. Owns the slider state and
 * hands the narrowed match list to its render prop, so the feed re-renders as
 * the bar moves. Defaults to the search's own persisted floor.
 */
export function MatchFilter({
  matches,
  initialMinScore,
  children
}: {
  matches: PostingMatch[];
  initialMinScore: number;
  children: (filtered: PostingMatch[]) => ReactNode;
}) {
  const [minScore, setMinScore] = useState(initialMinScore);
  const filtered = filterMatchesByScore(matches, minScore);

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-1 rounded-lg border border-border bg-muted px-4 py-3 sm:max-w-sm">
        <MinScoreSlider value={minScore} onChange={setMinScore} label="Minimum score" />
        <p data-testid="match-count" className="font-mono text-[11px] text-subdued">
          {filtered.length} of {matches.length} {matches.length === 1 ? "match" : "matches"}
        </p>
      </div>
      {children(filtered)}
    </div>
  );
}
