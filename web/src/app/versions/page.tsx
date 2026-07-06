"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { getProfile, listVersions } from "@/lib/api";
import { useDevUser } from "@/components/providers/dev-user-provider";

export default function VersionsPage() {
  const { selectedUserId } = useDevUser();

  const profileQuery = useQuery({
    queryKey: ["profile", selectedUserId],
    queryFn: () => getProfile(selectedUserId as string),
    enabled: selectedUserId !== null,
    retry: false
  });

  const profileId = profileQuery.data?.id;
  const versionsQuery = useQuery({
    queryKey: ["versions", profileId],
    queryFn: () => listVersions(profileId as string),
    enabled: Boolean(profileId)
  });

  const versions = versionsQuery.data ?? [];

  return (
    <section className="space-y-6">
      <div>
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-accent">Versions</p>
        <h1 className="mt-3 text-3xl font-semibold text-text">Version history</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-subdued">
          Every tailored resume, with its job-target context and ATS score. Open one to see the
          before/after diff, or compare any two.
        </p>
      </div>

      {profileQuery.isLoading || versionsQuery.isLoading ? (
        <p className="text-sm text-subdued">Loading versions…</p>
      ) : !profileQuery.data ? (
        <div className="rounded-lg border border-border bg-muted p-8">
          <h2 className="text-lg font-semibold text-text">No profile yet</h2>
          <p className="mt-1 text-sm text-subdued">
            Upload a resume on the{" "}
            <Link href="/profile" className="text-accent hover:underline">
              Profile
            </Link>{" "}
            screen first.
          </p>
        </div>
      ) : versions.length === 0 ? (
        <div className="rounded-lg border border-border bg-muted p-8">
          <h2 className="text-lg font-semibold text-text">No versions yet</h2>
          <p className="mt-1 text-sm text-subdued">
            Generate a kit from a{" "}
            <Link href="/job-targets" className="text-accent hover:underline">
              job target
            </Link>{" "}
            to create your first tailored version.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-muted">
          {versions.map((version) => (
            <li key={version.id}>
              <Link
                href={`/versions/${version.id}`}
                className="flex items-center justify-between gap-4 px-5 py-4 transition hover:bg-surface"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-text">
                    {version.label ?? "Untitled version"}
                  </p>
                  <p className="mt-0.5 text-xs text-subdued">
                    {version.job_target
                      ? `${version.job_target.company ?? "—"}${
                          version.job_target.title ? ` · ${version.job_target.title}` : ""
                        }`
                      : "Base version"}
                    {" · "}
                    <span className="font-mono">{version.template_id}</span>
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {version.headline_score !== null && version.headline_score !== undefined ? (
                    <span className="rounded border border-accent/40 px-1.5 py-0.5 font-mono text-xs text-accent">
                      {version.headline_score.toFixed(0)}
                    </span>
                  ) : (
                    <span className="font-mono text-xs text-subdued">—</span>
                  )}
                  <span className="font-mono text-[11px] text-subdued">
                    {(version.document_availability.rendered_formats ?? []).join(" · ") ||
                      "not rendered"}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
