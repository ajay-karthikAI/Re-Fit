/** "3 days ago" style relative time for posting freshness on the feed. */
export function formatRelative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) {
    return "date unknown";
  }
  const then = new Date(iso);
  const seconds = Math.round((now.getTime() - then.getTime()) / 1000);
  if (Number.isNaN(seconds)) {
    return "date unknown";
  }
  if (seconds < 45) {
    return "just now";
  }
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 60 * 60 * 24 * 365],
    ["month", 60 * 60 * 24 * 30],
    ["week", 60 * 60 * 24 * 7],
    ["day", 60 * 60 * 24],
    ["hour", 60 * 60],
    ["minute", 60]
  ];
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, unitSeconds] of units) {
    if (seconds >= unitSeconds) {
      return rtf.format(-Math.floor(seconds / unitSeconds), unit);
    }
  }
  return "just now";
}
