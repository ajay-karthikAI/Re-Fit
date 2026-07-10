"use client";

import { useState } from "react";

import type { ApplicationStatus } from "@/lib/api";
import {
  STATUS_LABELS,
  STATUS_ORDER,
  appliedAtFromDateInput,
  todayISODate
} from "@/lib/applications";

type StatusControlProps = {
  status: ApplicationStatus;
  onChange: (status: ApplicationStatus, appliedAt?: string) => void;
  disabled?: boolean;
};

/**
 * Inline segmented pipeline control. Choosing "applied" first prompts for the
 * applied date (defaults to today) because that date drives follow-up
 * scheduling; every other status change fires immediately.
 */
export function StatusControl({ status, onChange, disabled }: StatusControlProps) {
  const [appliedPromptOpen, setAppliedPromptOpen] = useState(false);
  const [appliedDate, setAppliedDate] = useState(todayISODate());

  const pick = (next: ApplicationStatus) => {
    if (next === status) {
      return;
    }
    if (next === "applied") {
      setAppliedDate(todayISODate());
      setAppliedPromptOpen(true);
      return;
    }
    setAppliedPromptOpen(false);
    onChange(next);
  };

  return (
    <div className="relative inline-block">
      <div
        role="radiogroup"
        aria-label="Application status"
        className="inline-flex rounded-md border border-border bg-surface p-0.5"
      >
        {STATUS_ORDER.map((option) => {
          const active = option === status;
          return (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={disabled}
              onClick={() => pick(option)}
              className={[
                "rounded px-2 py-1 text-xs transition disabled:opacity-50",
                active
                  ? option === "rejected"
                    ? "bg-danger/15 text-danger"
                    : "bg-muted text-accent"
                  : "text-subdued hover:text-text"
              ].join(" ")}
            >
              {STATUS_LABELS[option]}
            </button>
          );
        })}
      </div>

      {appliedPromptOpen ? (
        <div className="absolute left-0 top-full z-20 mt-1 w-60 rounded-md border border-border bg-surface p-3 shadow-panel">
          <label className="block text-xs text-subdued" htmlFor="applied-at-input">
            Applied on
            <span className="mt-1 block font-normal text-subdued/80">
              Drives follow-up scheduling.
            </span>
          </label>
          <input
            id="applied-at-input"
            type="date"
            value={appliedDate}
            onChange={(event) => setAppliedDate(event.target.value)}
            className="mt-2 w-full rounded-md border border-border bg-muted px-2 py-1.5 text-sm text-text outline-none focus:border-accent"
          />
          <div className="mt-3 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setAppliedPromptOpen(false)}
              className="rounded-md px-2 py-1 text-xs text-subdued hover:text-text"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => {
                setAppliedPromptOpen(false);
                onChange("applied", appliedAtFromDateInput(appliedDate));
              }}
              className="rounded-md bg-accent/15 px-2.5 py-1 text-xs font-medium text-accent hover:bg-accent/25"
            >
              Mark applied
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
