"use client";

import type { ApplyKitGap } from "@/lib/api";

export function GapBanner({
  gaps,
  onFill
}: {
  gaps: ApplyKitGap[];
  onFill: (field: string) => void;
}) {
  if (gaps.length === 0) {
    return null;
  }
  return (
    <div
      data-testid="gap-banner"
      className="rounded-xl border border-amber-500/40 bg-amber-950/20 p-4"
    >
      <p className="text-sm font-medium text-amber-100">
        {gaps.length} {gaps.length === 1 ? "answer only you can give" : "answers only you can give"}
      </p>
      <p className="mt-0.5 text-xs text-amber-200/80">
        refit never guesses facts like salary or work authorization. Add them once — they&apos;re
        reused on every application.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {gaps.map((gap) => (
          <button
            key={gap.field}
            type="button"
            data-testid={`gap-${gap.field}`}
            onClick={() => onFill(gap.field)}
            className="rounded-md border border-amber-500/50 bg-amber-500/10 px-3 py-1.5 text-xs font-medium text-amber-100 transition hover:border-amber-400/70"
          >
            Fill this in: {gap.label} →
          </button>
        ))}
      </div>
    </div>
  );
}
