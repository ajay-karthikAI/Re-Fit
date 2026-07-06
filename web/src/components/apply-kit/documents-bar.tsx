"use client";

import type { ApplyKitDocument } from "@/lib/api";

// Pinned near the top: in nearly every ATS the resume upload comes before any
// questions, so these are the first thing the applicant reaches for.
export function DocumentsBar({ documents }: { documents: ApplyKitDocument[] }) {
  return (
    <div
      data-testid="documents-bar"
      className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-muted p-4"
    >
      <p className="font-mono text-xs uppercase tracking-[0.16em] text-subdued">Attach first</p>
      {documents.map((doc) => (
        <a
          key={doc.key}
          href={doc.download_url ?? "#"}
          target="_blank"
          rel="noreferrer"
          data-testid={`document-${doc.key}`}
          aria-disabled={!doc.ready}
          className={[
            "inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-semibold transition",
            doc.ready
              ? "bg-accent text-background hover:bg-accent/90"
              : "pointer-events-none bg-surface text-subdued"
          ].join(" ")}
        >
          ↓ {doc.label}
        </a>
      ))}
    </div>
  );
}
