import { describe, expect, it } from "vitest";

import { appliedAtFromDateInput, dueState, followupGate } from "@/lib/applications";

describe("followupGate", () => {
  it("blocks everything while the application is a draft", () => {
    for (const kind of ["post_apply", "post_interview", "checkin"] as const) {
      const gate = followupGate(kind, "draft", null);
      expect(gate.allowed).toBe(false);
    }
  });

  it("blocks all kinds until applied_at is set, since it drives scheduling", () => {
    const gate = followupGate("post_apply", "applied", null);
    expect(gate).toEqual({
      allowed: false,
      reason: "Set the applied date first — it drives scheduling."
    });
  });

  it("allows post_apply and checkin once applied with a date", () => {
    expect(followupGate("post_apply", "applied", "2026-06-26T12:00:00Z").allowed).toBe(true);
    expect(followupGate("checkin", "applied", "2026-06-26T12:00:00Z").allowed).toBe(true);
  });

  it("gates post_interview behind interview status", () => {
    const gate = followupGate("post_interview", "applied", "2026-06-26T12:00:00Z");
    expect(gate).toEqual({
      allowed: false,
      reason: "Available once status reaches interview."
    });
    expect(followupGate("post_interview", "interview", "2026-06-26T12:00:00Z").allowed).toBe(
      true
    );
    expect(followupGate("post_interview", "offer", "2026-06-26T12:00:00Z").allowed).toBe(true);
  });

  it("does not treat rejected as having reached interview", () => {
    expect(followupGate("post_interview", "rejected", "2026-06-26T12:00:00Z").allowed).toBe(
      false
    );
    // ...but a graceful check-in after rejection is fine.
    expect(followupGate("checkin", "rejected", "2026-06-26T12:00:00Z").allowed).toBe(true);
  });
});

describe("dueState", () => {
  const today = new Date(2026, 6, 6); // July 6 2026, local time

  it("flags past send_after dates as overdue", () => {
    expect(dueState("2026-07-03", today)).toBe("overdue");
  });

  it("flags today as due", () => {
    expect(dueState("2026-07-06", today)).toBe("due");
  });

  it("flags future dates as scheduled and missing dates as null", () => {
    expect(dueState("2026-07-10", today)).toBe("scheduled");
    expect(dueState(null, today)).toBeNull();
  });
});

describe("appliedAtFromDateInput", () => {
  it("pins the date to midday UTC so it survives timezone round-trips", () => {
    expect(appliedAtFromDateInput("2026-07-06")).toBe("2026-07-06T12:00:00Z");
  });
});
