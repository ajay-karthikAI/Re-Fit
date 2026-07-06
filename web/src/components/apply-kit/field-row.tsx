"use client";

import type { ApplyKitDocument, ApplyKitField } from "@/lib/api";
import { stripMarkdown } from "@/lib/strip-markdown";
import { CopyButton } from "@/components/apply-kit/copy-button";
import { useCopyField } from "@/components/apply-kit/use-copy-field";

export function isProseField(field: ApplyKitField): boolean {
  return field.field_spec.question_kind != null;
}

function isUploadField(field: ApplyKitField): boolean {
  return field.field_spec.source === "generated" && field.field_spec.question_kind == null;
}

const RELOAD_ICON = "↻";

function ValueBox({ value, tall }: { value: string; tall?: boolean }) {
  return (
    <pre
      data-testid="field-value"
      className={[
        "mt-1 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-background/70 px-3 py-2 font-mono text-[13px] leading-6 text-text",
        tall ? "max-h-52" : ""
      ].join(" ")}
    >
      {value}
    </pre>
  );
}

export function FieldRow({
  field,
  document,
  regenerating,
  onRegenerate,
  onFillGap
}: {
  field: ApplyKitField;
  document?: ApplyKitDocument;
  regenerating?: boolean;
  onRegenerate?: (fieldKey: string) => void;
  onFillGap?: (field: ApplyKitField) => void;
}) {
  const { copy, copiedKey } = useCopyField();
  const spec = field.field_spec;
  const key = spec.key;
  const prose = isProseField(field);
  const upload = isUploadField(field);

  return (
    <div className="py-3" data-testid={`field-${key}`} data-status={field.status}>
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-medium text-text">{spec.label}</p>
        {prose && onRegenerate ? (
          <button
            type="button"
            data-testid={`regenerate-${key}`}
            aria-label="Regenerate this answer"
            disabled={regenerating}
            onClick={() => onRegenerate(key)}
            className="shrink-0 rounded-md border border-border px-2 py-1 font-mono text-xs text-subdued transition hover:border-accent hover:text-accent disabled:opacity-50"
          >
            <span className={regenerating ? "inline-block animate-spin" : ""}>{RELOAD_ICON}</span>
          </button>
        ) : null}
      </div>

      {/* Upload fields point at the rendered document rather than a copyable value. */}
      {upload ? (
        document ? (
          <a
            href={document.download_url ?? "#"}
            target="_blank"
            rel="noreferrer"
            data-testid={`download-${key}`}
            className="mt-1 inline-flex items-center gap-1.5 rounded-md border border-accent/50 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition hover:bg-accent/20"
          >
            ↓ Download {spec.label.toLowerCase()}
          </a>
        ) : (
          <p className="mt-1 text-xs text-subdued">Document not ready yet.</p>
        )
      ) : null}

      {/* A generated short answer that failed verification, surfaced not dropped. */}
      {field.status === "error" ? (
        <div className="mt-1 rounded-md border border-red-500/40 bg-red-950/20 px-3 py-2 text-xs text-red-200">
          Couldn&apos;t generate this answer: {field.error ?? "unknown error"}.{" "}
          <button
            type="button"
            onClick={() => onRegenerate?.(key)}
            className="underline underline-offset-2 hover:text-red-100"
          >
            Try again
          </button>
        </div>
      ) : null}

      {/* Missing answer-profile fact: nudge to the profile, never guess it. */}
      {field.status === "needs_user_input" ? (
        <button
          type="button"
          data-testid={`fill-${key}`}
          onClick={() => onFillGap?.(field)}
          className="mt-1 inline-flex items-center gap-1 rounded-md border border-amber-500/40 bg-amber-950/20 px-3 py-1.5 text-xs text-amber-200 transition hover:border-amber-400/60"
        >
          Add this to your answer profile →
        </button>
      ) : null}

      {field.status === "manual_only" ? (
        <p className="mt-1 text-xs text-subdued">
          Select this yourself on the form — refit never auto-fills self-identification.
        </p>
      ) : null}

      {/* Resolved, copyable value (contact facts, answer-profile facts, short answers). */}
      {field.status === "ready" && !upload && field.resolved_value != null ? (
        <div className={regenerating ? "animate-pulse opacity-60" : ""}>
          <ValueBox value={field.resolved_value} tall={prose} />
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {prose ? (
              <>
                <CopyButton
                  copyKey={key}
                  label="Copy as plain text"
                  text={stripMarkdown(field.resolved_value)}
                  copy={copy}
                  copiedKey={copiedKey}
                  primary
                />
                <CopyButton
                  copyKey={`${key}-md`}
                  label="Copy markdown"
                  text={field.resolved_value}
                  copy={copy}
                  copiedKey={copiedKey}
                />
              </>
            ) : (
              <CopyButton
                copyKey={key}
                label="Copy"
                text={field.resolved_value}
                copy={copy}
                copiedKey={copiedKey}
                primary
              />
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
