"use client";

import { useEffect, useState } from "react";

/** Metallic score tiers shared by the dashboard and the job feed:
 *  gold ≥85, silver ≥70, dim below. */
export function scoreTone(score: number): { text: string; bar: string } {
  if (score >= 85) {
    return { text: "text-accent", bar: "bg-gold-bar" };
  }
  if (score >= 70) {
    return { text: "text-silver", bar: "bg-silver-bar" };
  }
  return { text: "text-faint", bar: "bg-silver-bar" };
}

/** A progress bar that animates its fill from 0 to `pct` on mount. */
export function Bar({
  pct,
  fill,
  className = ""
}: {
  pct: number;
  fill: string;
  className?: string;
}) {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const raf = requestAnimationFrame(() => requestAnimationFrame(() => setWidth(pct)));
    return () => cancelAnimationFrame(raf);
  }, [pct]);
  return (
    <div className={`overflow-hidden rounded-full bg-silver/[0.12] ${className}`}>
      <div
        className={`h-full rounded-full ${fill} transition-[width] duration-[1200ms] ease-[cubic-bezier(.22,1,.36,1)]`}
        style={{ width: `${width}%` }}
      />
    </div>
  );
}

/** Right-aligned "NN%" over an animated fill bar — the match-score treatment
 *  from the dashboard's matched-postings rows. */
export function ScoreBar({ score, className = "" }: { score: number; className?: string }) {
  const tone = scoreTone(score);
  return (
    <div className={`grid w-[92px] shrink-0 justify-items-end gap-[5px] ${className}`}>
      <span className={`font-mono text-[13px] font-medium ${tone.text}`}>
        {Math.round(score)}%
      </span>
      <Bar pct={score} fill={tone.bar} className="h-[5px] w-full" />
    </div>
  );
}
