"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import {
  type ApplicationListItem,
  type ApplicationStatus,
  type PostingMatch,
  type SourceBoard,
  listApplications,
  listMatches,
  listSavedSearches,
  listSourceBoards
} from "@/lib/api";
import { useDevUser } from "@/components/providers/dev-user-provider";
import { Bar, ScoreBar } from "@/components/ui/score-bar";
import { formatRelative } from "@/lib/relative-time";

/* ── animation primitives (mirror the mockup's count-up + bar reveal) ── */

function useCountUp(target: number, suffix = ""): string {
  const [text, setText] = useState(`0${suffix}`);
  useEffect(() => {
    let raf: number;
    const t0 = performance.now();
    const dur = 1100;
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      setText(`${Math.round(target * eased)}${suffix}`);
      if (p < 1) {
        raf = requestAnimationFrame(tick);
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, suffix]);
  return text;
}

const SOURCE_LABELS: Record<string, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  rss: "RSS feeds"
};

const STATUS_PILLS: Record<ApplicationStatus, { label: string; cls: string }> = {
  draft: { label: "DRAFT", cls: "text-silver border-silver/30" },
  applied: { label: "APPLIED", cls: "text-success border-success/40" },
  interview: { label: "INTERVIEW", cls: "text-accent border-accent/[0.45]" },
  offer: { label: "OFFER", cls: "text-success border-success/40" },
  rejected: { label: "REJECTED", cls: "text-faint border-silver/20" }
};

function shortAgo(iso: string | null): string {
  if (!iso) {
    return "never";
  }
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

function greeting(now: Date = new Date()): string {
  const h = now.getHours();
  if (h < 12) return "Good morning.";
  if (h < 18) return "Good afternoon.";
  return "Good evening.";
}

const DAY_MS = 24 * 60 * 60 * 1000;

/* ── panels ── */

function StatCard({
  label,
  value,
  suffix,
  delta,
  deltaTone
}: {
  label: string;
  value: number;
  suffix?: string;
  delta: string;
  deltaTone: "gold" | "silver";
}) {
  const text = useCountUp(value, suffix ?? "");
  return (
    <div className="rounded-[14px] border border-silver/[0.14] bg-[linear-gradient(180deg,rgba(232,196,107,0.04),transparent_60%)] p-5 transition-colors duration-[250ms] hover:border-accent/[0.45]">
      <div className="mb-3 font-mono text-[11px] tracking-[0.1em] text-silver">{label}</div>
      <div className="flex items-baseline gap-2">
        <span className="text-[32px] font-bold leading-none text-text">{text}</span>
        <span
          className={`font-mono text-xs ${deltaTone === "gold" ? "text-accent" : "text-silver"}`}
        >
          {delta}
        </span>
      </div>
    </div>
  );
}

function PanelEmpty({ children }: { children: React.ReactNode }) {
  return <p className="px-5 py-4 text-[13px] text-faint">{children}</p>;
}

export function AurumDashboard() {
  const { selectedUserId } = useDevUser();

  const searchesQuery = useQuery({
    queryKey: ["saved-searches", selectedUserId],
    queryFn: () => listSavedSearches(selectedUserId as string),
    enabled: selectedUserId !== null
  });
  const searchIds = (searchesQuery.data ?? []).map((s) => s.id);

  const matchesQuery = useQuery({
    queryKey: ["dashboard-matches", searchIds],
    queryFn: async () => {
      const lists = await Promise.all(searchIds.map((id) => listMatches(id)));
      const seen = new Set<string>();
      const merged: PostingMatch[] = [];
      for (const match of lists.flat()) {
        if (!seen.has(match.posting_id)) {
          seen.add(match.posting_id);
          merged.push(match);
        }
      }
      return merged.sort((a, b) => b.score - a.score);
    },
    enabled: searchIds.length > 0
  });

  const applicationsQuery = useQuery({
    queryKey: ["applications", selectedUserId],
    queryFn: () => listApplications(selectedUserId as string),
    enabled: selectedUserId !== null
  });

  const boardsQuery = useQuery({
    queryKey: ["source-boards"],
    queryFn: listSourceBoards,
    enabled: selectedUserId !== null
  });

  const matches = matchesQuery.data ?? [];
  const applications = applicationsQuery.data ?? [];
  const boards = boardsQuery.data ?? [];

  const now = Date.now();
  const newToday = matches.filter(
    (m) => now - new Date(m.computed_at).getTime() < DAY_MS
  ).length;
  const kitsThisWeek = applications.filter(
    (a) => a.last_activity_at && now - new Date(a.last_activity_at).getTime() < 7 * DAY_MS
  ).length;
  const avgScore =
    matches.length > 0
      ? Math.round(matches.reduce((sum, m) => sum + m.score, 0) / matches.length)
      : 0;
  const topScore = matches.length > 0 ? Math.round(matches[0].score) : 0;
  const attentionBoards = boards.filter(
    (b) => b.needs_attention || b.health !== "healthy"
  ).length;

  // Group boards by source, like the mockup's "Greenhouse · 4 companies" rows.
  const boardGroups = Object.entries(
    boards.reduce<Record<string, SourceBoard[]>>((acc, board) => {
      (acc[board.source] ??= []).push(board);
      return acc;
    }, {})
  ).map(([source, group]) => {
    const dot = group.some((b) => b.health === "dead")
      ? "bg-danger"
      : group.some((b) => b.needs_attention || b.health !== "healthy")
        ? "bg-accent"
        : "bg-success";
    const lastSync = group
      .map((b) => b.last_success_at)
      .filter(Boolean)
      .sort()
      .at(-1);
    return {
      key: source,
      name: `${SOURCE_LABELS[source] ?? source} · ${group.length} ${
        group.length === 1 ? "company" : "companies"
      }`,
      dot,
      meta: lastSync ? `synced ${shortAgo(lastSync as string)}` : "never synced"
    };
  });

  const recentKits = [...applications]
    .sort((a, b) => (b.last_activity_at ?? "").localeCompare(a.last_activity_at ?? ""))
    .slice(0, 3);

  const subtitle =
    matches.length === 0
      ? "Add source boards and a saved search to start matching postings."
      : newToday > 0
        ? `${newToday} new ${newToday === 1 ? "posting" : "postings"} matched your profile since yesterday.`
        : "No new postings matched your profile since yesterday.";

  return (
    <div className="grid gap-7">
      {/* GREETING */}
      <div>
        <div className="mb-2.5 font-mono text-xs tracking-[0.14em] text-accent">DASHBOARD</div>
        <h1 className="m-0 mb-1.5 text-[clamp(26px,3vw,34px)] font-bold tracking-[-0.02em]">
          {greeting()}
        </h1>
        <p className="m-0 text-[15px] text-subdued">{subtitle}</p>
      </div>

      {/* STAT CARDS */}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4">
        <StatCard
          label="MATCHED POSTINGS"
          value={matches.length}
          delta={newToday > 0 ? `+${newToday} today` : "none today"}
          deltaTone={newToday > 0 ? "gold" : "silver"}
        />
        <StatCard
          label="KITS GENERATED"
          value={applications.length}
          delta={kitsThisWeek > 0 ? `+${kitsThisWeek} this week` : "none this week"}
          deltaTone={kitsThisWeek > 0 ? "gold" : "silver"}
        />
        <StatCard
          label="AVG MATCH SCORE"
          value={avgScore}
          suffix="%"
          delta={matches.length > 0 ? `top ${topScore}%` : "no matches"}
          deltaTone={matches.length > 0 ? "gold" : "silver"}
        />
        <StatCard
          label="BOARDS WATCHED"
          value={boards.length}
          delta={
            attentionBoards > 0
              ? `${attentionBoards} syncing`
              : boards.length > 0
                ? "all healthy"
                : "none yet"
          }
          deltaTone="silver"
        />
      </div>

      {/* TWO-COLUMN: postings + side panel */}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(340px,1fr))] items-start gap-5">
        {/* MATCHED POSTINGS */}
        <section className="min-w-0 overflow-hidden rounded-2xl border border-silver/[0.14]">
          <div className="flex items-center justify-between gap-3 border-b border-silver/10 px-5 py-[18px]">
            <div>
              <div className="text-[17px] font-semibold">Matched postings</div>
              <div className="mt-0.5 text-[13px] text-faint">Scored against your profile</div>
            </div>
            <Link href="/job-feed" className="font-mono text-xs text-accent">
              VIEW ALL →
            </Link>
          </div>
          <div>
            {matchesQuery.isLoading && searchIds.length > 0 ? (
              <PanelEmpty>Loading matches…</PanelEmpty>
            ) : matches.length === 0 ? (
              <PanelEmpty>
                No matches yet — add boards on{" "}
                <Link href="/settings/source-boards" className="text-accent">
                  Source Boards
                </Link>{" "}
                and create a saved search.
              </PanelEmpty>
            ) : (
              matches.slice(0, 5).map((posting) => (
                <a
                  key={posting.posting_id}
                  href={posting.url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex cursor-pointer items-center gap-3.5 border-b border-silver/[0.07] px-5 py-3.5 transition-colors duration-200 hover:bg-accent/5"
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[9px] border border-silver/[0.15] bg-silver/10 text-sm font-bold text-silver">
                    {(posting.company_name || "?").charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="overflow-hidden text-ellipsis whitespace-nowrap text-[14.5px] font-semibold text-text">
                      {posting.title}
                    </div>
                    <div className="mt-0.5 text-[12.5px] text-faint">
                      {posting.company_name} · {formatRelative(posting.posted_at)}
                    </div>
                  </div>
                  <ScoreBar score={posting.score} />
                </a>
              ))
            )}
          </div>
        </section>

        {/* SIDE PANEL */}
        <div className="grid min-w-0 gap-5">
          {/* SOURCE BOARDS */}
          <section className="rounded-2xl border border-silver/[0.14] p-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="text-[17px] font-semibold">Source boards</div>
              <Link href="/settings/source-boards" className="font-mono text-xs text-accent">
                MANAGE →
              </Link>
            </div>
            <div className="grid gap-3">
              {boards.length === 0 ? (
                <p className="text-[13px] text-faint">No boards watched yet.</p>
              ) : (
                boardGroups.map((group) => (
                  <div key={group.key} className="flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2.5">
                      <span
                        className={`h-[7px] w-[7px] shrink-0 rounded-full ${group.dot}`}
                      />
                      <span className="overflow-hidden text-ellipsis whitespace-nowrap text-sm text-silver">
                        {group.name}
                      </span>
                    </div>
                    <span className="shrink-0 font-mono text-xs text-faint">{group.meta}</span>
                  </div>
                ))
              )}
            </div>
          </section>

          {/* RECENT KITS */}
          <section className="rounded-2xl border border-accent/[0.35] bg-[linear-gradient(180deg,rgba(232,196,107,0.06),transparent_65%)] p-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="text-[17px] font-semibold">Recent kits</div>
              <Link href="/versions" className="font-mono text-xs text-accent">
                VERSIONS →
              </Link>
            </div>
            <div className="grid gap-3">
              {recentKits.length === 0 ? (
                <p className="text-[13px] text-faint">No kits yet.</p>
              ) : (
                recentKits.map((application) => {
                  const pill = STATUS_PILLS[application.status];
                  return (
                    <div
                      key={application.id}
                      className="flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <div className="overflow-hidden text-ellipsis whitespace-nowrap text-sm font-medium text-text">
                          {application.company ?? "Unknown"} — {application.title ?? "role"}
                        </div>
                        <div className="mt-0.5 font-mono text-[11.5px] text-faint">
                          {application.resume_version_label ?? "unlabeled"} ·{" "}
                          {formatRelative(application.last_activity_at)}
                        </div>
                      </div>
                      <span
                        className={`shrink-0 rounded-full border px-2.5 py-1 font-mono text-[11px] ${pill.cls}`}
                      >
                        {pill.label}
                      </span>
                    </div>
                  );
                })
              )}
            </div>
            <Link
              href="/job-feed"
              className="mt-[18px] block rounded-[10px] bg-gold-gradient p-3 text-center text-[14.5px] font-bold text-onaccent transition hover:-translate-y-0.5 hover:shadow-gold"
            >
              Generate tailored kit
            </Link>
          </section>
        </div>
      </div>
    </div>
  );
}

/* Sidebar plan card + usage bar, exported for the shell. */
export function PlanCard() {
  return (
    <div className="mt-auto grid gap-2 rounded-xl border border-silver/[0.14] p-3.5">
      <div className="font-mono text-[11px] tracking-[0.1em] text-silver">PRO PLAN</div>
      <div className="text-[13px] leading-[1.45] text-subdued">
        12 of 20 tailored kits used this month
      </div>
      <Bar pct={60} fill="bg-gold-bar" className="h-1.5" />
    </div>
  );
}
