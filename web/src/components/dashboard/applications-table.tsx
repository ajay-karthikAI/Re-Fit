"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Fragment, useEffect, useMemo, useState } from "react";

import {
  type ApplicationListItem,
  type ApplicationStatus,
  listApplications,
  updateApplication
} from "@/lib/api";
import { STATUS_LABELS, STATUS_ORDER, formatDate, formatScore } from "@/lib/applications";
import { useDevUser } from "@/components/providers/dev-user-provider";
import { StatusControl } from "@/components/dashboard/status-control";
import { KitPanel } from "@/components/dashboard/kit-panel";
import { useToast } from "@/components/ui/toast";

function ScoreBadge({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined) {
    return <span className="font-mono text-xs text-subdued">—</span>;
  }
  const tone =
    score >= 75 ? "text-accent border-accent/40" : score >= 50 ? "text-yellow-300 border-yellow-500/40" : "text-red-300 border-red-500/40";
  return (
    <span className={`rounded border px-1.5 py-0.5 font-mono text-xs ${tone}`}>
      {formatScore(score)}
    </span>
  );
}

function KitDot({ ready, label }: { ready: boolean; label: string }) {
  return (
    <span
      title={`${label}: ${ready ? "ready" : "missing"}`}
      className={[
        "inline-flex h-6 min-w-6 items-center justify-center rounded border px-1 font-mono text-[11px]",
        ready ? "border-accent/40 text-accent" : "border-dashed border-border text-subdued"
      ].join(" ")}
    >
      {label}
    </span>
  );
}

function KitIndicator({ application }: { application: ApplicationListItem }) {
  return (
    <span className="inline-flex gap-1">
      <KitDot ready={application.resume_pdf_ready} label="PDF" />
      <KitDot ready={application.has_cover_letter} label="CL" />
      <KitDot ready={application.followup_count > 0} label={`FU ${application.followup_count}`} />
    </span>
  );
}

function EmptyState() {
  const steps = [
    {
      href: "/profile",
      title: "Upload your resume",
      body: "Parse it into a structured profile — the single source of truth for every fact."
    },
    {
      href: "/job-targets",
      title: "Add a job target",
      body: "Paste the job description; requirements are extracted and weighted."
    },
    {
      href: "/job-targets",
      title: "Generate a kit",
      body: "Tailored resume, verified cover letter, and follow-ups — tracked here."
    }
  ];
  return (
    <div className="rounded-lg border border-border bg-muted p-8" data-testid="empty-state">
      <h2 className="text-lg font-semibold text-text">No applications yet</h2>
      <p className="mt-1 max-w-xl text-sm text-subdued">
        Every row in this tracker records exactly which resume version went out. Three steps to
        your first one:
      </p>
      <ol className="mt-6 grid gap-4 sm:grid-cols-3">
        {steps.map((step, index) => (
          <li key={step.title} className="rounded-md border border-border bg-surface p-4">
            <span className="font-mono text-xs text-accent">{index + 1}</span>
            <Link href={step.href} className="mt-2 block text-sm font-medium text-text hover:text-accent">
              {step.title} →
            </Link>
            <p className="mt-1 text-xs leading-5 text-subdued">{step.body}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function ApplicationsTable() {
  const { selectedUserId } = useDevUser();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Deep link from the kit "Track application" flow: ?application=<id> expands
  // that row on arrival. Read from the URL rather than useSearchParams to avoid
  // the prerender Suspense requirement.
  useEffect(() => {
    const target = new URLSearchParams(window.location.search).get("application");
    if (target) {
      setExpandedId(target);
    }
  }, []);

  const listKey = ["applications", selectedUserId];
  const applicationsQuery = useQuery({
    queryKey: listKey,
    queryFn: () => listApplications(selectedUserId as string),
    enabled: selectedUserId !== null
  });

  const statusMutation = useMutation({
    mutationFn: ({
      applicationId,
      status,
      appliedAt
    }: {
      applicationId: string;
      status: ApplicationStatus;
      appliedAt?: string;
    }) =>
      updateApplication(applicationId, {
        status,
        ...(appliedAt ? { applied_at: appliedAt } : {})
      }),
    onMutate: async ({ applicationId, status, appliedAt }) => {
      await queryClient.cancelQueries({ queryKey: listKey });
      const previous = queryClient.getQueryData<ApplicationListItem[]>(listKey);
      queryClient.setQueryData<ApplicationListItem[]>(listKey, (rows) =>
        (rows ?? []).map((row) =>
          row.id === applicationId
            ? { ...row, status, ...(appliedAt ? { applied_at: appliedAt } : {}) }
            : row
        )
      );
      return { previous };
    },
    onError: (error: Error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(listKey, context.previous);
      }
      toast(`Status update failed: ${error.message}`);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: listKey });
    }
  });

  const rows = useMemo(() => applicationsQuery.data ?? [], [applicationsQuery.data]);
  const counts = useMemo(() => {
    const map = new Map<ApplicationStatus, number>();
    for (const row of rows) {
      map.set(row.status, (map.get(row.status) ?? 0) + 1);
    }
    return map;
  }, [rows]);
  const visible = statusFilter ? rows.filter((row) => row.status === statusFilter) : rows;

  if (!selectedUserId || applicationsQuery.isLoading) {
    return <p className="text-sm text-subdued">Loading applications…</p>;
  }
  if (applicationsQuery.error) {
    return (
      <div className="rounded-md border border-red-500/40 bg-red-950/20 p-4 text-sm text-red-200">
        Could not load applications from FastAPI.
      </div>
    );
  }
  if (rows.length === 0) {
    return <EmptyState />;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2" data-testid="status-chips">
        <button
          type="button"
          onClick={() => setStatusFilter(null)}
          className={[
            "rounded-full border px-3 py-1 text-xs transition",
            statusFilter === null
              ? "border-accent/50 bg-accent/10 text-accent"
              : "border-border text-subdued hover:text-text"
          ].join(" ")}
        >
          All {rows.length}
        </button>
        {STATUS_ORDER.map((status) => {
          const count = counts.get(status) ?? 0;
          if (count === 0) {
            return null;
          }
          const active = statusFilter === status;
          return (
            <button
              key={status}
              type="button"
              onClick={() => setStatusFilter(active ? null : status)}
              className={[
                "rounded-full border px-3 py-1 text-xs transition",
                active
                  ? "border-accent/50 bg-accent/10 text-accent"
                  : "border-border text-subdued hover:text-text"
              ].join(" ")}
            >
              {STATUS_LABELS[status]} {count}
            </button>
          );
        })}
      </div>

      <div className="overflow-x-auto rounded-lg border border-border bg-muted">
        <table className="w-full min-w-[880px] border-collapse text-left">
          <thead>
            <tr className="border-b border-border font-mono text-[11px] uppercase tracking-[0.14em] text-subdued">
              <th className="px-4 py-3 font-normal">Company / Role</th>
              <th className="px-4 py-3 font-normal">Status</th>
              <th className="px-4 py-3 font-normal">Applied</th>
              <th className="px-4 py-3 font-normal">ATS</th>
              <th className="px-4 py-3 font-normal">Kit</th>
              <th className="px-4 py-3 font-normal">Last activity</th>
              <th className="w-10 px-2 py-3" />
            </tr>
          </thead>
          <tbody>
            {visible.map((application) => {
              const expanded = expandedId === application.id;
              return (
                <Fragment key={application.id}>
                  <tr
                    data-testid="application-row"
                    className={[
                      "border-b border-border/60 transition",
                      expanded ? "bg-surface" : "hover:bg-surface/60"
                    ].join(" ")}
                  >
                    <td className="px-4 py-3">
                      <p className="text-sm font-medium text-text">
                        {application.company ?? "Unknown company"}
                      </p>
                      <p className="text-xs text-subdued">{application.title ?? "—"}</p>
                      <p className="mt-1 font-mono text-[11px] text-subdued/80">
                        {application.resume_version_label ?? "unlabeled version"}
                      </p>
                    </td>
                    <td className="px-4 py-3 align-middle">
                      <StatusControl
                        status={application.status}
                        disabled={statusMutation.isPending}
                        onChange={(status, appliedAt) =>
                          statusMutation.mutate({
                            applicationId: application.id,
                            status,
                            appliedAt
                          })
                        }
                      />
                    </td>
                    <td className="px-4 py-3 text-sm text-subdued">
                      {formatDate(application.applied_at)}
                    </td>
                    <td className="px-4 py-3">
                      <ScoreBadge score={application.ats_score} />
                    </td>
                    <td className="px-4 py-3">
                      <KitIndicator application={application} />
                    </td>
                    <td className="px-4 py-3 text-sm text-subdued">
                      {formatDate(application.last_activity_at)}
                    </td>
                    <td className="px-2 py-3 text-right">
                      <button
                        type="button"
                        aria-expanded={expanded}
                        aria-label={expanded ? "Collapse kit" : "Expand kit"}
                        onClick={() => setExpandedId(expanded ? null : application.id)}
                        className="rounded-md border border-border px-2 py-1 text-xs text-subdued transition hover:border-accent hover:text-text"
                      >
                        {expanded ? "▲" : "▼"}
                      </button>
                    </td>
                  </tr>
                  {expanded ? (
                    <tr className="border-b border-border/60 bg-background/40">
                      <td colSpan={7} className="p-0">
                        <KitPanel application={application} />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
