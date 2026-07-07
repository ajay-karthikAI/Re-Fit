"use client";

// The kit POST is synchronous (tailor + score + letter + render in one request),
// so we advance a staged indicator on a timer while it is in flight and snap to
// done when the real result lands. Shared by the job-target Generate panel and
// the job feed's one-click Generate-kit so the "instant" moment looks the same
// wherever a kit is produced.
export const STAGES = [
  "Tailoring resume to the job",
  "Scoring against requirements",
  "Writing the cover letter",
  "Rendering documents"
];
export const STAGE_INTERVAL_MS = 1800;

export function ProgressStepper({ activeStage }: { activeStage: number }) {
  return (
    <ol className="space-y-2" data-testid="generate-progress">
      {STAGES.map((stage, index) => {
        const done = index < activeStage;
        const active = index === activeStage;
        return (
          <li key={stage} className="flex items-center gap-3 text-sm">
            <span
              className={[
                "flex h-6 w-6 items-center justify-center rounded-full border font-mono text-xs",
                done
                  ? "border-accent bg-accent/15 text-accent"
                  : active
                    ? "border-accent text-accent"
                    : "border-border text-subdued"
              ].join(" ")}
            >
              {done ? "✓" : index + 1}
            </span>
            <span className={active || done ? "text-text" : "text-subdued"}>
              {stage}
              {active ? <span className="ml-1 animate-pulse text-accent">…</span> : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
