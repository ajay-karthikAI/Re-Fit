"use client";

import { useQuery } from "@tanstack/react-query";

import { listDigests } from "@/lib/api";
import { formatRelative } from "@/lib/relative-time";

/**
 * Digest history for a saved search — mostly a trust-building "did it actually
 * run last night" view over the persisted digests rows (generation only; not a
 * delivery feature).
 */
export function DigestHistory({ savedSearchId }: { savedSearchId: string }) {
  const query = useQuery({
    queryKey: ["digests", savedSearchId],
    queryFn: () => listDigests(savedSearchId)
  });

  const digests = query.data ?? [];

  return (
    <section className="space-y-3">
      <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-accent">Digest history</h2>
      {query.isLoading ? (
        <p className="text-sm text-subdued">Loading digest history…</p>
      ) : digests.length === 0 ? (
        <p className="text-sm text-subdued">
          No digests generated yet — they run nightly once postings are ingested.
        </p>
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-muted">
          {digests.map((digest) => (
            <li
              key={digest.id}
              data-testid="digest-row"
              className="flex items-center justify-between gap-4 px-4 py-3 text-sm"
            >
              <span className="text-text">
                {digest.new_match_count} new {digest.new_match_count === 1 ? "match" : "matches"}
              </span>
              <span className="font-mono text-[11px] text-subdued">
                {formatRelative(digest.created_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
