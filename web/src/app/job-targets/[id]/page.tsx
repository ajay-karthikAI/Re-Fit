"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";

import { getJobTarget } from "@/lib/api";
import { GeneratePanel } from "@/components/kit/generate-panel";
import { RequirementsChips } from "@/components/job-targets/requirements-chips";

type Requirements = Parameters<typeof RequirementsChips>[0]["requirements"];

export default function JobTargetDetailPage() {
  const params = useParams<{ id: string }>();
  const jobTargetId = params.id;

  const query = useQuery({
    queryKey: ["job-target", jobTargetId],
    queryFn: () => getJobTarget(jobTargetId),
    enabled: Boolean(jobTargetId)
  });

  if (query.isLoading) {
    return <p className="text-sm text-subdued">Loading job target…</p>;
  }
  if (query.error || !query.data) {
    return (
      <div className="rounded-md border border-red-500/40 bg-red-950/20 p-4 text-sm text-red-200">
        Could not load this job target.
      </div>
    );
  }

  const target = query.data;
  const requirements = (target.extracted_requirements as Requirements | null) ?? null;

  return (
    <section className="space-y-8">
      <div>
        <Link href="/job-targets" className="font-mono text-xs text-subdued hover:text-text">
          ← Job targets
        </Link>
        <h1 className="mt-3 text-3xl font-semibold text-text">
          {target.company ?? "Untitled company"}
        </h1>
        {target.title ? <p className="mt-1 text-lg text-subdued">{target.title}</p> : null}
        {target.source_url ? (
          <a
            href={target.source_url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-block text-xs text-accent underline-offset-4 hover:underline"
          >
            {target.source_url}
          </a>
        ) : null}
      </div>

      <GeneratePanel jobTargetId={jobTargetId} hasRequirements={requirements !== null} />

      <div className="grid gap-8 lg:grid-cols-2">
        <div>
          <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-accent">Requirements</h2>
          <div className="mt-4">
            <RequirementsChips requirements={requirements} />
          </div>
        </div>
        <div>
          <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-accent">
            Job description
          </h2>
          <div className="mt-4 max-h-[28rem] overflow-y-auto whitespace-pre-wrap rounded-lg border border-border bg-muted p-4 text-sm leading-6 text-subdued">
            {target.raw_description}
          </div>
        </div>
      </div>
    </section>
  );
}
