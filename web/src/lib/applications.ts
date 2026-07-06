import type { ApplicationStatus, FollowupKind } from "@/lib/api";

export const STATUS_ORDER: ApplicationStatus[] = [
  "draft",
  "applied",
  "interview",
  "rejected",
  "offer"
];

export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  draft: "Draft",
  applied: "Applied",
  interview: "Interview",
  rejected: "Rejected",
  offer: "Offer"
};

export const FOLLOWUP_KIND_LABELS: Record<FollowupKind, string> = {
  post_apply: "Post-apply",
  post_interview: "Post-interview",
  checkin: "Check-in"
};

export const FOLLOWUP_KINDS: FollowupKind[] = ["post_apply", "post_interview", "checkin"];

/** Statuses at or past "applied" — the application actually went out. */
const APPLIED_OR_LATER: ApplicationStatus[] = ["applied", "interview", "rejected", "offer"];

/** Statuses at or past "interview" (a rejection may predate any interview, so it doesn't count). */
const INTERVIEW_OR_LATER: ApplicationStatus[] = ["interview", "offer"];

export type FollowupGate = { allowed: true } | { allowed: false; reason: string };

/**
 * Whether a follow-up of `kind` can be generated for an application.
 * Follow-up scheduling is driven by applied_at, so every kind needs it.
 */
export function followupGate(
  kind: FollowupKind,
  status: ApplicationStatus,
  appliedAt: string | null
): FollowupGate {
  if (kind === "post_interview" && !INTERVIEW_OR_LATER.includes(status)) {
    return { allowed: false, reason: "Available once status reaches interview." };
  }
  if (!APPLIED_OR_LATER.includes(status)) {
    return { allowed: false, reason: "Move the application to applied first." };
  }
  if (!appliedAt) {
    return { allowed: false, reason: "Set the applied date first — it drives scheduling." };
  }
  return { allowed: true };
}

export type DueState = "overdue" | "due" | "scheduled";

/** send_after is a plain YYYY-MM-DD date; compare in local time against today. */
export function dueState(sendAfter: string | null, today: Date = new Date()): DueState | null {
  if (!sendAfter) {
    return null;
  }
  const todayStr = [
    today.getFullYear(),
    String(today.getMonth() + 1).padStart(2, "0"),
    String(today.getDate()).padStart(2, "0")
  ].join("-");
  if (sendAfter < todayStr) {
    return "overdue";
  }
  if (sendAfter === todayStr) {
    return "due";
  }
  return "scheduled";
}

/** Today as YYYY-MM-DD in local time, for the applied-at date input default. */
export function todayISODate(now: Date = new Date()): string {
  return [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0")
  ].join("-");
}

/**
 * A date-input value (YYYY-MM-DD) as an applied_at datetime. Midday UTC so the
 * date survives timezone round-trips on both sides.
 */
export function appliedAtFromDateInput(date: string): string {
  return `${date}T12:00:00Z`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) {
    return "—";
  }
  const date = new Date(iso.length === 10 ? `${iso}T12:00:00Z` : iso);
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric"
  }).format(date);
}

export function formatScore(score: number | null | undefined): string {
  return score === null || score === undefined ? "—" : score.toFixed(0);
}
