"use client";

import type { PostingMatch } from "@/lib/api";
import { GenerateKitButton } from "@/components/job-feed/generate-kit-button";
import { ScoreBar } from "@/components/ui/score-bar";
import { formatRelative } from "@/lib/relative-time";

export function PostingCard({ match, userId }: { match: PostingMatch; userId: string }) {
  return (
    <li
      data-testid="posting-card"
      className="flex flex-col gap-4 rounded-xl border border-border bg-muted p-5 sm:flex-row sm:items-start sm:justify-between"
    >
      <div className="min-w-0 space-y-2">
        <h3 className="text-base font-semibold text-text">{match.title}</h3>
        <p className="text-sm text-subdued">
          <span className="text-text">{match.company_name}</span>
          {match.location ? <span> · {match.location}</span> : null}
          {match.department ? <span> · {match.department}</span> : null}
        </p>
        <p className="font-mono text-[11px] text-subdued">{formatRelative(match.posted_at)}</p>
        {match.missing_terms.length > 0 ? (
          <div className="flex flex-wrap gap-1.5 pt-1">
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-subdued">
              Missing
            </span>
            {match.missing_terms.slice(0, 6).map((term) => (
              <span
                key={term}
                className="rounded-full border border-dashed border-border px-2 py-0.5 text-[11px] text-subdued"
              >
                {term}
              </span>
            ))}
          </div>
        ) : null}
      </div>
      <div className="flex shrink-0 flex-row items-center gap-4 sm:flex-col sm:items-end">
        <ScoreBar score={match.score} />
        <GenerateKitButton postingId={match.posting_id} userId={userId} />
      </div>
    </li>
  );
}
