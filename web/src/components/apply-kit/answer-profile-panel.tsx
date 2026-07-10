"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import {
  type AnswerProfileWrite,
  getAnswerProfile,
  saveAnswerProfile
} from "@/lib/api";
import { useToast } from "@/components/ui/toast";

const WORK_AUTH = [
  "citizen",
  "permanent_resident",
  "visa_holder",
  "needs_sponsorship",
  "other"
] as const;
const RELOCATION = ["yes", "no", "case_by_case"] as const;
const SALARY_TYPE = ["annual", "hourly"] as const;

type FormState = {
  work_auth: (typeof WORK_AUTH)[number];
  sponsorship_needed: boolean;
  relocation: (typeof RELOCATION)[number];
  salary_type: (typeof SALARY_TYPE)[number];
  salary_min: string;
  salary_max: string;
  salary_currency: string;
  referral_source_default: string;
  notice_period_days: string;
  pronouns: string;
};

const EMPTY: FormState = {
  work_auth: "citizen",
  sponsorship_needed: false,
  relocation: "case_by_case",
  salary_type: "annual",
  salary_min: "",
  salary_max: "",
  salary_currency: "USD",
  referral_source_default: "",
  notice_period_days: "",
  pronouns: ""
};

function toWrite(form: FormState): AnswerProfileWrite {
  const number = (value: string) => (value.trim() === "" ? null : Number(value));
  return {
    work_auth: form.work_auth,
    sponsorship_needed: form.sponsorship_needed,
    relocation: form.relocation,
    salary_type: form.salary_type,
    salary_min: number(form.salary_min),
    salary_max: number(form.salary_max),
    salary_currency: form.salary_currency || "USD",
    referral_source_default: form.referral_source_default || null,
    notice_period_days: number(form.notice_period_days),
    pronouns: form.pronouns || null,
    eeo_prefs: null
  };
}

const FIELD_LABEL = "block text-xs font-medium text-subdued";
const INPUT =
  "mt-1 w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm text-text focus:border-accent focus:outline-none";

/** Slide-over so the user fills a missing fact without navigating away and
 * losing their place mid-application. */
export function AnswerProfilePanel({
  userId,
  focusField,
  onClose,
  onSaved
}: {
  userId: string;
  focusField: string | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [form, setForm] = useState<FormState>(EMPTY);
  const [errors, setErrors] = useState<string[]>([]);
  const firstFieldRef = useRef<HTMLElement | null>(null);

  const profileQuery = useQuery({
    queryKey: ["answer-profile", userId],
    queryFn: () => getAnswerProfile(userId)
  });

  useEffect(() => {
    const data = profileQuery.data;
    if (!data) {
      return;
    }
    setForm({
      work_auth: data.work_auth,
      sponsorship_needed: data.sponsorship_needed,
      relocation: data.relocation,
      salary_type: data.salary_type,
      salary_min: data.salary_min?.toString() ?? "",
      salary_max: data.salary_max?.toString() ?? "",
      salary_currency: data.salary_currency ?? "USD",
      referral_source_default: data.referral_source_default ?? "",
      notice_period_days: data.notice_period_days?.toString() ?? "",
      pronouns: data.pronouns ?? ""
    });
  }, [profileQuery.data]);

  // Pre-focus the field the gap pointed at (link_target ?field=...).
  useEffect(() => {
    if (!profileQuery.isLoading && focusField) {
      const el = document.getElementById(`ap-${focusField}`);
      el?.focus();
    }
  }, [focusField, profileQuery.isLoading]);

  const mutation = useMutation({
    mutationFn: async () => {
      const result = await saveAnswerProfile(userId, toWrite(form));
      if (!result.ok) {
        throw new Error(result.errors.map((error) => error.msg).join("; "));
      }
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["answer-profile", userId] });
      toast("Answer profile saved.", "success");
      onSaved();
      onClose();
    },
    onError: (error: Error) => setErrors([error.message])
  });

  const set = <K extends keyof FormState>(field: K, value: FormState[K]) =>
    setForm((current) => ({ ...current, [field]: value }));

  const highlight = (field: string) =>
    focusField === field ? "rounded-md ring-1 ring-accent/60 p-2 -m-2" : "";

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute inset-0 bg-black/50"
      />
      <div
        data-testid="answer-profile-panel"
        className="relative z-10 flex h-full w-full max-w-md flex-col border-l border-border bg-surface shadow-panel"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-text">Answer profile</h2>
            <p className="text-xs text-subdued">Reused on every application — fill it once.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border px-2 py-1 text-xs text-subdued hover:border-accent hover:text-text"
          >
            Close
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
          <div className={highlight("work_auth")}>
            <label htmlFor="ap-work_auth" className={FIELD_LABEL}>
              Work authorization
            </label>
            <select
              id="ap-work_auth"
              ref={firstFieldRef as never}
              value={form.work_auth}
              onChange={(event) => set("work_auth", event.target.value as FormState["work_auth"])}
              className={INPUT}
            >
              {WORK_AUTH.map((option) => (
                <option key={option} value={option}>
                  {option.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </div>

          <div className={highlight("sponsorship_needed")}>
            <label htmlFor="ap-sponsorship_needed" className="flex items-center gap-2 text-sm text-text">
              <input
                id="ap-sponsorship_needed"
                type="checkbox"
                checked={form.sponsorship_needed}
                onChange={(event) => set("sponsorship_needed", event.target.checked)}
              />
              I now or in the future require sponsorship
            </label>
          </div>

          <div className={highlight("relocation")}>
            <label htmlFor="ap-relocation" className={FIELD_LABEL}>
              Willing to relocate
            </label>
            <select
              id="ap-relocation"
              value={form.relocation}
              onChange={(event) => set("relocation", event.target.value as FormState["relocation"])}
              className={INPUT}
            >
              {RELOCATION.map((option) => (
                <option key={option} value={option}>
                  {option.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className={highlight("salary_min")}>
              <label htmlFor="ap-salary_min" className={FIELD_LABEL}>
                Salary min
              </label>
              <input
                id="ap-salary_min"
                type="number"
                value={form.salary_min}
                onChange={(event) => set("salary_min", event.target.value)}
                className={INPUT}
              />
            </div>
            <div className={highlight("salary_max")}>
              <label htmlFor="ap-salary_max" className={FIELD_LABEL}>
                Salary max
              </label>
              <input
                id="ap-salary_max"
                type="number"
                value={form.salary_max}
                onChange={(event) => set("salary_max", event.target.value)}
                className={INPUT}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="ap-salary_type" className={FIELD_LABEL}>
                Salary type
              </label>
              <select
                id="ap-salary_type"
                value={form.salary_type}
                onChange={(event) =>
                  set("salary_type", event.target.value as FormState["salary_type"])
                }
                className={INPUT}
              >
                {SALARY_TYPE.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="ap-salary_currency" className={FIELD_LABEL}>
                Currency
              </label>
              <input
                id="ap-salary_currency"
                value={form.salary_currency}
                onChange={(event) => set("salary_currency", event.target.value)}
                className={INPUT}
              />
            </div>
          </div>

          <div className={highlight("referral_source_default")}>
            <label htmlFor="ap-referral_source_default" className={FIELD_LABEL}>
              Default referral source
            </label>
            <input
              id="ap-referral_source_default"
              value={form.referral_source_default}
              onChange={(event) => set("referral_source_default", event.target.value)}
              className={INPUT}
            />
          </div>

          {errors.length > 0 ? (
            <div className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
              {errors.join("; ")}
            </div>
          ) : null}
        </div>

        <div className="border-t border-border px-5 py-4">
          <button
            type="button"
            data-testid="save-answer-profile"
            disabled={mutation.isPending}
            onClick={() => {
              setErrors([]);
              mutation.mutate();
            }}
            className="w-full rounded-[10px] bg-gold-gradient px-4 py-2 text-sm font-bold text-background transition enabled:hover:-translate-y-0.5 enabled:hover:shadow-gold disabled:opacity-50"
          >
            {mutation.isPending ? "Saving…" : "Save & return to kit"}
          </button>
        </div>
      </div>
    </div>
  );
}
