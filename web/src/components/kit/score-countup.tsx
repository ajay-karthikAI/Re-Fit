"use client";

import { useEffect, useRef, useState } from "react";

/** Ease-out so the number decelerates as it lands on the after-score. */
function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/**
 * The product's money moment: the ATS score counting up from before → after.
 * Big number, animated once on mount. Respects prefers-reduced-motion.
 */
export function ScoreCountUp({
  before,
  after,
  durationMs = 1400
}: {
  before: number;
  after: number;
  durationMs?: number;
}) {
  const [value, setValue] = useState(before);
  const frame = useRef<number>();

  useEffect(() => {
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || before === after) {
      setValue(after);
      return;
    }

    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / durationMs);
      setValue(before + (after - before) * easeOutCubic(progress));
      if (progress < 1) {
        frame.current = requestAnimationFrame(tick);
      }
    };
    frame.current = requestAnimationFrame(tick);
    return () => {
      if (frame.current) {
        cancelAnimationFrame(frame.current);
      }
    };
  }, [before, after, durationMs]);

  const delta = after - before;
  const landed = Math.abs(value - after) < 0.05;

  return (
    <div className="flex flex-col items-center gap-2 py-6" data-testid="score-countup">
      <p className="font-mono text-xs uppercase tracking-[0.24em] text-subdued">
        ATS score after tailoring
      </p>
      <div className="flex items-end gap-4">
        <span className="font-mono text-sm text-subdued">{before.toFixed(0)}</span>
        <span
          data-testid="score-value"
          data-landed={landed ? "true" : "false"}
          className="text-7xl font-semibold tabular-nums text-accent"
        >
          {value.toFixed(1)}
        </span>
        {delta !== 0 ? (
          <span
            className={[
              "mb-2 rounded px-2 py-0.5 font-mono text-sm",
              delta > 0 ? "bg-accent/15 text-accent" : "bg-danger/15 text-danger"
            ].join(" ")}
          >
            {delta > 0 ? "+" : ""}
            {delta.toFixed(1)}
          </span>
        ) : null}
      </div>
    </div>
  );
}
