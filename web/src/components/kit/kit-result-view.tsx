"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { type KitResult, createApplication } from "@/lib/api";
import { useDevUser } from "@/components/providers/dev-user-provider";
import { ScoreCountUp } from "@/components/kit/score-countup";
import { useToast } from "@/components/ui/toast";

function DownloadLink({ label, url }: { label: string; url: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-text transition hover:border-accent"
    >
      {label}
    </a>
  );
}

export function KitResultView({
  kit,
  jobTargetId
}: {
  kit: KitResult;
  jobTargetId: string;
}) {
  const { selectedUserId } = useDevUser();
  const router = useRouter();
  const { toast } = useToast();

  const before = kit.score_before.headline_score;
  const after = kit.score_after.headline_score;
  const missing = kit.score_after.keyword_coverage.missing_terms ?? [];
  const summary = kit.diff_summary;

  const trackMutation = useMutation({
    mutationFn: () =>
      createApplication(selectedUserId as string, {
        job_target_id: jobTargetId,
        resume_version_id: kit.resume_version_id,
        status: "draft"
      }),
    onSuccess: (application) => {
      toast("Application tracked.", "success");
      router.push(`/dashboard?application=${application.id}`);
    },
    onError: (error: Error) => toast(`Could not track application: ${error.message}`)
  });

  return (
    <div className="space-y-6" data-testid="kit-result">
      <div className="rounded-xl border border-border bg-muted">
        <ScoreCountUp before={before} after={after} />
        <div className="grid gap-px border-t border-border bg-border sm:grid-cols-3">
          <div className="bg-muted p-4 text-center">
            <p className="font-mono text-xs text-subdued">Bullets rewritten</p>
            <p className="mt-1 text-2xl font-semibold text-text">{summary.bullet_rewrites}</p>
          </div>
          <div className="bg-muted p-4 text-center">
            <p className="font-mono text-xs text-subdued">Changes</p>
            <p className="mt-1 text-2xl font-semibold text-text">{summary.changes}</p>
          </div>
          <div className="bg-muted p-4 text-center">
            <p className="font-mono text-xs text-subdued">Skills reordered</p>
            <p className="mt-1 text-2xl font-semibold text-text">
              {summary.skills_reordered ? "Yes" : "No"}
            </p>
          </div>
        </div>
      </div>

      {missing.length > 0 ? (
        <div>
          <p className="text-xs text-subdued">Still missing from the resume:</p>
          <div className="mt-2 flex flex-wrap gap-1">
            {missing.map((term) => (
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

      <div className="flex flex-wrap items-center gap-2">
        <DownloadLink label="Download resume PDF" url={kit.resume_pdf_url} />
        <DownloadLink label="Download cover letter PDF" url={kit.cover_letter_pdf_url} />
        <button
          type="button"
          data-testid="track-application"
          disabled={trackMutation.isPending || !selectedUserId}
          onClick={() => trackMutation.mutate()}
          className="rounded-md bg-accent/15 px-4 py-2 text-sm font-medium text-accent transition hover:bg-accent/25 disabled:opacity-50"
        >
          {trackMutation.isPending ? "Tracking…" : "Track application →"}
        </button>
      </div>
    </div>
  );
}
