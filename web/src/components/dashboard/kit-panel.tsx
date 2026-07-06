"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import {
  type ApplicationKitDetail,
  type ApplicationListItem,
  type FollowupKind,
  type KitFollowup,
  createFollowup,
  getApplicationKit,
  renderVersion
} from "@/lib/api";
import {
  FOLLOWUP_KINDS,
  FOLLOWUP_KIND_LABELS,
  dueState,
  followupGate,
  formatDate
} from "@/lib/applications";
import { MarkdownProse } from "@/components/ui/markdown";
import { useToast } from "@/components/ui/toast";

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="font-mono text-xs uppercase tracking-[0.18em] text-subdued">{children}</h3>
  );
}

function ScorePair({ before, after }: { before: number | null; after: number | null }) {
  return (
    <p className="text-2xl font-semibold text-text">
      <span className="text-subdued">{before === null ? "—" : before.toFixed(1)}</span>
      <span className="mx-2 text-subdued">→</span>
      <span className="text-accent">{after === null ? "—" : after.toFixed(1)}</span>
    </p>
  );
}

function DownloadButton({
  label,
  url,
  onRender,
  rendering
}: {
  label: string;
  url: string | null;
  onRender: () => void;
  rendering: boolean;
}) {
  if (url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        data-testid={`download-${label.toLowerCase()}`}
        className="rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-text transition hover:border-accent"
      >
        Download {label}
      </a>
    );
  }
  return (
    <button
      type="button"
      onClick={onRender}
      disabled={rendering}
      className="rounded-md border border-dashed border-border px-3 py-1.5 text-xs text-subdued transition hover:border-accent hover:text-text disabled:opacity-50"
    >
      {rendering ? "Rendering…" : `Render ${label}`}
    </button>
  );
}

function FollowupCard({ followup }: { followup: KitFollowup }) {
  const { toast } = useToast();
  const due = dueState(followup.send_after ?? null);
  return (
    <div className="rounded-md border border-border bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-text">
          {FOLLOWUP_KIND_LABELS[followup.kind]}
        </span>
        {followup.send_after ? (
          <span
            className={[
              "rounded px-1.5 py-0.5 font-mono text-[11px]",
              due === "overdue"
                ? "bg-red-950/60 text-red-300"
                : due === "due"
                  ? "bg-accent/15 text-accent"
                  : "text-subdued"
            ].join(" ")}
          >
            {due === "overdue" ? "overdue · " : due === "due" ? "due today · " : "send after "}
            {formatDate(followup.send_after)}
          </span>
        ) : (
          <span className="font-mono text-[11px] text-subdued">unscheduled</span>
        )}
      </div>
      <p className="mt-2 truncate text-xs text-subdued" title={followup.subject}>
        {followup.subject}
      </p>
      <button
        type="button"
        onClick={async () => {
          await navigator.clipboard.writeText(
            `Subject: ${followup.subject}\n\n${followup.body_markdown}`
          );
          toast("Follow-up copied to clipboard.", "success");
        }}
        className="mt-2 rounded-md border border-border px-2 py-1 text-xs text-subdued transition hover:border-accent hover:text-text"
      >
        Copy subject + body
      </button>
    </div>
  );
}

export function KitPanel({ application }: { application: ApplicationListItem }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [renderingFormat, setRenderingFormat] = useState<"pdf" | "docx" | null>(null);

  const kitQuery = useQuery({
    queryKey: ["application-kit", application.id],
    queryFn: () => getApplicationKit(application.id)
  });

  const renderMutation = useMutation({
    mutationFn: ({ versionId, format }: { versionId: string; format: "pdf" | "docx" }) =>
      renderVersion(versionId, format),
    onMutate: ({ format }) => setRenderingFormat(format),
    onSettled: () => setRenderingFormat(null),
    onSuccess: (result) => {
      window.open(result.download_url, "_blank", "noreferrer");
      queryClient.invalidateQueries({ queryKey: ["application-kit", application.id] });
      queryClient.invalidateQueries({ queryKey: ["applications"] });
    },
    onError: (error: Error) => toast(`Render failed: ${error.message}`)
  });

  const followupMutation = useMutation({
    mutationFn: (kind: FollowupKind) => createFollowup(application.id, kind),
    onSuccess: () => {
      toast("Follow-up generated and verified.", "success");
      queryClient.invalidateQueries({ queryKey: ["application-kit", application.id] });
      queryClient.invalidateQueries({ queryKey: ["applications"] });
    },
    onError: (error: Error) => toast(`Follow-up generation failed: ${error.message}`)
  });

  if (kitQuery.isLoading) {
    return <p className="p-5 text-sm text-subdued">Loading kit…</p>;
  }
  if (kitQuery.error || !kitQuery.data) {
    return (
      <p className="p-5 text-sm text-red-300">
        Could not load the kit for this application.
      </p>
    );
  }

  const kit: ApplicationKitDetail = kitQuery.data;
  const version = kit.resume_version;
  const followups = kit.followups ?? [];

  return (
    <div className="grid gap-4 p-4 lg:grid-cols-3" data-testid="kit-panel">
      <section className="rounded-lg border border-border bg-muted/60 p-4">
        <SectionTitle>Resume version</SectionTitle>
        <p className="mt-2 text-sm font-medium text-text">{version.label ?? "Untitled version"}</p>
        <p className="mt-1 text-xs text-subdued">
          Template <span className="font-mono">{version.template_id}</span> · created{" "}
          {formatDate(version.created_at)}
        </p>
        <div className="mt-3">
          <ScorePair before={version.score_before ?? null} after={version.score_after ?? null} />
          <p className="text-xs text-subdued">ATS score, before → after tailoring</p>
        </div>
        {version.missing_terms && version.missing_terms.length > 0 ? (
          <div className="mt-3">
            <p className="text-xs text-subdued">Still missing:</p>
            <div className="mt-1 flex flex-wrap gap-1">
              {version.missing_terms.map((term) => (
                <span
                  key={term}
                  className="rounded border border-border px-1.5 py-0.5 text-[11px] text-subdued"
                >
                  {term}
                </span>
              ))}
            </div>
          </div>
        ) : null}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <DownloadButton
            label="PDF"
            url={version.pdf_url ?? null}
            rendering={renderingFormat === "pdf"}
            onRender={() => renderMutation.mutate({ versionId: version.id, format: "pdf" })}
          />
          <DownloadButton
            label="DOCX"
            url={version.docx_url ?? null}
            rendering={renderingFormat === "docx"}
            onRender={() => renderMutation.mutate({ versionId: version.id, format: "docx" })}
          />
          <Link
            href={`/versions/${version.id}`}
            className="text-xs text-accent underline-offset-4 hover:underline"
          >
            View diff
          </Link>
        </div>
      </section>

      <section className="rounded-lg border border-border bg-muted/60 p-4">
        <SectionTitle>Cover letter</SectionTitle>
        {kit.cover_letter ? (
          <>
            <div className="mt-2 flex items-center gap-2 text-xs text-subdued">
              <span className="rounded border border-border px-1.5 py-0.5 font-mono text-[11px]">
                {kit.cover_letter.tone}
              </span>
              <span>{kit.cover_letter.word_count} words</span>
            </div>
            <p
              className={[
                "mt-2 text-xs",
                kit.cover_letter.claims.passed ? "text-accent" : "text-red-300"
              ].join(" ")}
            >
              {kit.cover_letter.claims.passed
                ? `All ${kit.cover_letter.claims.claims_checked} claims verified against your profile and the job post.`
                : `${(kit.cover_letter.claims.violations ?? []).length} unverified claim(s) — regenerate before sending.`}
            </p>
            <div className="mt-3 max-h-56 overflow-y-auto rounded-md border border-border bg-surface p-3">
              <MarkdownProse markdown={kit.cover_letter.body_markdown} />
            </div>
            {kit.cover_letter.pdf_url ? (
              <a
                href={kit.cover_letter.pdf_url}
                target="_blank"
                rel="noreferrer"
                className="mt-3 inline-block rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-text transition hover:border-accent"
              >
                Download PDF
              </a>
            ) : null}
          </>
        ) : (
          <p className="mt-2 text-sm text-subdued">
            No cover letter yet. Generate the kit from the job target.
          </p>
        )}
      </section>

      <section className="rounded-lg border border-border bg-muted/60 p-4">
        <SectionTitle>Follow-ups</SectionTitle>
        <div className="mt-2 space-y-2">
          {followups.length === 0 ? (
            <p className="text-sm text-subdued">None generated yet.</p>
          ) : (
            followups.map((followup) => (
              <FollowupCard key={followup.id} followup={followup} />
            ))
          )}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {FOLLOWUP_KINDS.map((kind) => {
            const gate = followupGate(kind, application.status, application.applied_at ?? null);
            return (
              <button
                key={kind}
                type="button"
                disabled={!gate.allowed || followupMutation.isPending}
                title={gate.allowed ? undefined : gate.reason}
                onClick={() => followupMutation.mutate(kind)}
                className="rounded-md border border-border px-2.5 py-1.5 text-xs text-subdued transition enabled:hover:border-accent enabled:hover:text-text disabled:cursor-not-allowed disabled:opacity-45"
              >
                {followupMutation.isPending && followupMutation.variables === kind
                  ? "Generating…"
                  : `Generate ${FOLLOWUP_KIND_LABELS[kind].toLowerCase()}`}
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
