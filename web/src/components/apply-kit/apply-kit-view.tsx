"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  type ApplyKit,
  getApplyKit,
  regenerateApplyKitField,
  trackJobTarget
} from "@/lib/api";
import { useDevUser } from "@/components/providers/dev-user-provider";
import { AnswerProfilePanel } from "@/components/apply-kit/answer-profile-panel";
import { ApplyTimerControl, useApplyTimer } from "@/components/apply-kit/apply-timer";
import { DocumentsBar } from "@/components/apply-kit/documents-bar";
import { FieldRow } from "@/components/apply-kit/field-row";
import { GapBanner } from "@/components/apply-kit/gap-banner";
import { useToast } from "@/components/ui/toast";

// Which rendered document backs each "upload" field on the form.
const DOCUMENT_FOR_FIELD: Record<string, string> = {
  resume_upload: "resume_pdf",
  cover_letter_upload: "cover_letter_pdf"
};

export function ApplyKitView({ jobTargetId }: { jobTargetId: string }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { selectedUserId } = useDevUser();
  const timer = useApplyTimer();
  const queryKey = ["apply-kit", jobTargetId];

  const [regeneratingKey, setRegeneratingKey] = useState<string | null>(null);
  const [gapField, setGapField] = useState<string | null>(null);

  const kitQuery = useQuery({
    queryKey,
    queryFn: () => getApplyKit(jobTargetId),
    // First assembly can tailor + render + generate; give it room and don't retry.
    staleTime: 60_000,
    retry: false
  });

  const regenerate = useMutation({
    mutationFn: (fieldKey: string) => regenerateApplyKitField(jobTargetId, fieldKey),
    onMutate: (fieldKey) => setRegeneratingKey(fieldKey),
    onSuccess: (kit) => {
      queryClient.setQueryData<ApplyKit>(queryKey, kit);
      toast("Answer regenerated.", "success");
    },
    onError: (error: Error) => toast(`Regenerate failed: ${error.message}`),
    onSettled: () => setRegeneratingKey(null)
  });

  const track = useMutation({
    mutationFn: () => trackJobTarget(jobTargetId),
    onSuccess: () => {
      timer.stop();
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast("Tracked in your dashboard.", "success");
    },
    onError: (error: Error) => toast(`Could not track: ${error.message}`)
  });

  if (kitQuery.isLoading) {
    return (
      <div className="rounded-xl border border-border bg-muted p-6">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-accent">
          Assembling apply kit
        </p>
        <p className="mt-1 text-sm text-subdued">
          Tailoring the resume, rendering documents, and drafting answers — first load only.
        </p>
      </div>
    );
  }

  if (kitQuery.error || !kitQuery.data) {
    return (
      <div className="rounded-md border border-red-500/40 bg-red-950/20 p-4 text-sm text-red-200">
        Couldn&apos;t assemble the apply kit: {(kitQuery.error as Error)?.message ?? "unknown error"}
      </div>
    );
  }

  const kit = kitQuery.data;
  const fieldsByKey = Object.fromEntries(kit.field_plan.map((item) => [item.field_spec.key, item]));

  let lastSection: string | null = null;

  return (
    <div className="space-y-5" data-testid="apply-kit">
      {/* Top bar: open the real posting (starts the timer) + the timer itself. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {kit.source_url ? (
            <a
              href={kit.source_url}
              target="_blank"
              rel="noreferrer"
              data-testid="open-posting"
              onClick={() => timer.start()}
              className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-background transition hover:bg-accent/90"
            >
              ↗ Open posting
            </a>
          ) : (
            <span className="text-xs text-subdued">No posting URL on this job target.</span>
          )}
          <span className="rounded-md border border-border px-2 py-1 font-mono text-[11px] uppercase tracking-wide text-subdued">
            {kit.source_ats}
          </span>
        </div>
        <ApplyTimerControl {...timer} />
      </div>

      <DocumentsBar documents={kit.documents} />

      <GapBanner gaps={kit.answer_profile_gaps} onFill={(field) => setGapField(field)} />

      {/* Fields in the exact checklist order — top to bottom is the real form. */}
      <div className="divide-y divide-border rounded-xl border border-border bg-muted px-4">
        {kit.checklist.map((step) => {
          const showSection = step.section !== lastSection;
          lastSection = step.section;
          const sectionHeader = showSection ? (
            <p
              key={`section-${step.order}`}
              className="pt-4 font-mono text-[11px] uppercase tracking-[0.18em] text-accent"
            >
              {step.section}
            </p>
          ) : null;

          if (step.field_key == null) {
            // Terminal submit step: track + stop the stopwatch.
            return (
              <div key={step.order}>
                {sectionHeader}
                <div className="flex items-center justify-between py-4">
                  <p className="text-sm text-subdued">{step.label}</p>
                  <button
                    type="button"
                    data-testid="track-application"
                    disabled={track.isPending || !selectedUserId}
                    onClick={() => track.mutate()}
                    className="rounded-md bg-accent/15 px-4 py-2 text-sm font-medium text-accent transition hover:bg-accent/25 disabled:opacity-50"
                  >
                    {track.isPending ? "Tracking…" : "I've submitted — track it"}
                  </button>
                </div>
              </div>
            );
          }

          const field = fieldsByKey[step.field_key];
          if (!field) {
            return null;
          }
          const documentKey = DOCUMENT_FOR_FIELD[step.field_key];
          const document = documentKey
            ? kit.documents.find((doc) => doc.key === documentKey)
            : undefined;

          return (
            <div key={step.order}>
              {sectionHeader}
              <FieldRow
                field={field}
                document={document}
                regenerating={regeneratingKey === step.field_key}
                onRegenerate={(fieldKey) => regenerate.mutate(fieldKey)}
                onFillGap={(f) => {
                  const backingField = f.field_spec.mapped_from?.split(".").slice(1).join(".");
                  setGapField(backingField ?? f.field_spec.key);
                }}
              />
            </div>
          );
        })}
      </div>

      {gapField != null && selectedUserId ? (
        <AnswerProfilePanel
          userId={selectedUserId}
          focusField={gapField}
          onClose={() => setGapField(null)}
          onSaved={() => queryClient.invalidateQueries({ queryKey })}
        />
      ) : null}
    </div>
  );
}
