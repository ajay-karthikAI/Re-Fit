"use client";

/**
 * The minimum-score control, shared by the new-search form (sets the search's
 * persisted floor) and the live feed filter (narrows the shown matches). A thin
 * controlled wrapper over a range input so it is trivial to test in isolation.
 */
export function MinScoreSlider({
  value,
  onChange,
  label = "Minimum score",
  id = "min-score"
}: {
  value: number;
  onChange: (value: number) => void;
  label?: string;
  id?: string;
}) {
  return (
    <div className="w-full">
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="font-mono text-xs uppercase tracking-[0.16em] text-subdued">
          {label}
        </label>
        <span data-testid="min-score-value" className="font-mono text-sm tabular-nums text-accent">
          {Math.round(value)}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={0}
        max={100}
        step={1}
        value={value}
        aria-label={label}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-2 w-full accent-accent"
      />
    </div>
  );
}
