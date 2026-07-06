"use client";

import { useCallback, useEffect, useState } from "react";

export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}m${String(seconds).padStart(2, "0")}s`;
}

/**
 * The dogfooding stopwatch behind the "Applied in 2m14s" exit criterion. Off by
 * default; starts on the first "Open posting" click and stops manually once the
 * user has actually submitted the real form.
 */
export function useApplyTimer() {
  const [enabled, setEnabled] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [stoppedAt, setStoppedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (startedAt == null || stoppedAt != null) {
      return;
    }
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [startedAt, stoppedAt]);

  const start = useCallback(() => {
    setStartedAt((current) => current ?? Date.now());
    setStoppedAt(null);
  }, []);
  const stop = useCallback(() => setStoppedAt((current) => current ?? Date.now()), []);
  const reset = useCallback(() => {
    setStartedAt(null);
    setStoppedAt(null);
  }, []);

  const elapsedMs = startedAt == null ? 0 : (stoppedAt ?? now) - startedAt;
  return {
    enabled,
    setEnabled,
    running: startedAt != null && stoppedAt == null,
    stopped: stoppedAt != null,
    elapsedMs,
    start,
    stop,
    reset
  };
}

type ApplyTimerControlProps = ReturnType<typeof useApplyTimer>;

export function ApplyTimerControl(timer: ApplyTimerControlProps) {
  if (!timer.enabled) {
    return (
      <button
        type="button"
        data-testid="timer-toggle"
        onClick={() => timer.setEnabled(true)}
        className="rounded-md border border-border px-2.5 py-1 font-mono text-xs text-subdued transition hover:border-accent hover:text-text"
      >
        ⏱ Timer
      </button>
    );
  }

  if (timer.stopped) {
    return (
      <div className="inline-flex items-center gap-2 rounded-md border border-accent/50 bg-accent/10 px-2.5 py-1 text-xs text-accent">
        <span data-testid="timer-final" className="font-mono">
          Applied in {formatDuration(timer.elapsedMs)}
        </span>
        <span aria-hidden>✓</span>
        <button
          type="button"
          onClick={timer.reset}
          className="font-mono text-subdued underline-offset-2 hover:text-text hover:underline"
        >
          reset
        </button>
      </div>
    );
  }

  return (
    <div className="inline-flex items-center gap-2 rounded-md border border-border bg-surface px-2.5 py-1 text-xs">
      <span
        data-testid="timer-elapsed"
        className={["font-mono text-text", timer.running ? "" : "text-subdued"].join(" ")}
      >
        ⏱ {formatDuration(timer.elapsedMs)}
      </span>
      {timer.running ? (
        <button
          type="button"
          data-testid="timer-stop"
          onClick={timer.stop}
          className="font-mono text-accent underline-offset-2 hover:underline"
        >
          stop
        </button>
      ) : (
        <span className="font-mono text-subdued">starts at “Open posting”</span>
      )}
    </div>
  );
}
