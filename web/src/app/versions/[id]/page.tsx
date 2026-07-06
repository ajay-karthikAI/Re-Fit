"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { compareVersions, getProfile, getVersionDiff, listVersions } from "@/lib/api";
import { useDevUser } from "@/components/providers/dev-user-provider";
import { DiffView } from "@/components/versions/diff-view";

export default function VersionDetailPage() {
  const params = useParams<{ id: string }>();
  const versionId = params.id;
  const { selectedUserId } = useDevUser();
  const [compareTo, setCompareTo] = useState<string>("");

  const diffQuery = useQuery({
    queryKey: ["version-diff", versionId],
    queryFn: () => getVersionDiff(versionId),
    enabled: Boolean(versionId)
  });

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

  const compareQuery = useQuery({
    queryKey: ["compare", versionId, compareTo],
    queryFn: () => compareVersions(versionId, compareTo),
    enabled: Boolean(compareTo)
  });

  const otherVersions = (versionsQuery.data ?? []).filter((version) => version.id !== versionId);
  const activeDiff = compareTo ? compareQuery.data : diffQuery.data;

  return (
    <section className="space-y-8">
      <div>
        <Link href="/versions" className="font-mono text-xs text-subdued hover:text-text">
          ← Versions
        </Link>
        <h1 className="mt-3 text-3xl font-semibold text-text">Version diff</h1>
        <p className="mt-2 text-sm text-subdued">
          {compareTo
            ? "Comparing this version against another."
            : "Changes from your base profile, grouped by role."}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="font-mono text-xs text-subdued" htmlFor="compare-picker">
          Compare with
        </label>
        <select
          id="compare-picker"
          value={compareTo}
          onChange={(event) => setCompareTo(event.target.value)}
          className="h-9 rounded-md border border-border bg-surface px-3 text-sm text-text outline-none focus:border-accent"
        >
          <option value="">Base profile (default diff)</option>
          {otherVersions.map((version) => (
            <option key={version.id} value={version.id}>
              {version.label ?? version.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </div>

      {(compareTo ? compareQuery.isLoading : diffQuery.isLoading) ? (
        <p className="text-sm text-subdued">Loading diff…</p>
      ) : activeDiff ? (
        <DiffView diff={activeDiff} />
      ) : (
        <div className="rounded-md border border-red-500/40 bg-red-950/20 p-4 text-sm text-red-200">
          Could not load the diff.
        </div>
      )}
    </section>
  );
}
