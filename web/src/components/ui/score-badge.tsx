import { formatScore } from "@/lib/applications";

/**
 * The ATS match-score badge, shared across Phase 2's dashboard and Phase 4's job
 * feed so a score reads identically wherever it appears: accent ≥75, amber ≥50,
 * red below.
 */
export function ScoreBadge({
  score,
  className = ""
}: {
  score: number | null | undefined;
  className?: string;
}) {
  if (score === null || score === undefined) {
    return <span className={`font-mono text-xs text-subdued ${className}`}>—</span>;
  }
  const tone =
    score >= 75
      ? "text-accent border-accent/40"
      : score >= 50
        ? "text-yellow-300 border-yellow-500/40"
        : "text-red-300 border-red-500/40";
  return (
    <span className={`rounded border px-1.5 py-0.5 font-mono text-xs ${tone} ${className}`}>
      {formatScore(score)}
    </span>
  );
}
