import { formatScore } from "@/lib/applications";

/**
 * The ATS match-score badge, shared across Phase 2's dashboard and Phase 4's job
 * feed so a score reads identically wherever it appears: gold ≥75, silver ≥50,
 * warm red below.
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
        ? "text-silver border-silver/40"
        : "text-danger border-danger/40";
  return (
    <span className={`rounded border px-1.5 py-0.5 font-mono text-xs ${tone} ${className}`}>
      {formatScore(score)}
    </span>
  );
}
