"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import {
  type BoardHealth,
  type SourceBoard,
  type SourceKind,
  createSourceBoard,
  deleteSourceBoard,
  listSourceBoards
} from "@/lib/api";
import { useDevUser } from "@/components/providers/dev-user-provider";
import { useToast } from "@/components/ui/toast";
import { formatRelative } from "@/lib/relative-time";

const SOURCES: { id: SourceKind; label: string; hint: string }[] = [
  { id: "greenhouse", label: "Greenhouse", hint: "board token, e.g. anthropic" },
  { id: "lever", label: "Lever", hint: "site, e.g. figma" },
  { id: "rss", label: "RSS / Atom", hint: "feed URL" }
];

const HEALTH_STYLES: Record<BoardHealth, string> = {
  healthy: "border-accent/40 text-accent",
  degraded: "border-yellow-500/40 text-yellow-300",
  dead: "border-red-500/40 text-red-300"
};

function HealthBadge({ health }: { health: BoardHealth }) {
  return (
    <span
      data-testid={`health-${health}`}
      className={`rounded border px-1.5 py-0.5 font-mono text-[11px] uppercase tracking-[0.12em] ${HEALTH_STYLES[health]}`}
    >
      {health}
    </span>
  );
}

function NewBoardForm({ userId }: { userId: string | null }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [source, setSource] = useState<SourceKind>("greenhouse");
  const [identifier, setIdentifier] = useState("");
  const [company, setCompany] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      createSourceBoard({
        source,
        identifier: identifier.trim(),
        company_name: company.trim(),
        user_id: userId
      }),
    onSuccess: () => {
      toast("Source board added.", "success");
      queryClient.invalidateQueries({ queryKey: ["source-boards"] });
      setIdentifier("");
      setCompany("");
    },
    onError: (error: Error) => toast(`Could not add board: ${error.message}`)
  });

  const hint = SOURCES.find((option) => option.id === source)?.hint ?? "";
  const canSubmit = identifier.trim().length > 0 && company.trim().length > 0 && !mutation.isPending;

  return (
    <form
      className="grid gap-3 rounded-xl border border-border bg-muted p-5 sm:grid-cols-[10rem_1fr_1fr_auto] sm:items-end"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit) {
          mutation.mutate();
        }
      }}
    >
      <div>
        <label htmlFor="board-source" className="font-mono text-xs uppercase tracking-[0.16em] text-subdued">
          Source
        </label>
        <select
          id="board-source"
          aria-label="Source"
          value={source}
          onChange={(event) => setSource(event.target.value as SourceKind)}
          className="mt-2 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent"
        >
          {SOURCES.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="board-identifier" className="font-mono text-xs uppercase tracking-[0.16em] text-subdued">
          Identifier
        </label>
        <input
          id="board-identifier"
          aria-label="Identifier"
          placeholder={hint}
          value={identifier}
          onChange={(event) => setIdentifier(event.target.value)}
          className="mt-2 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent"
        />
      </div>
      <div>
        <label htmlFor="board-company" className="font-mono text-xs uppercase tracking-[0.16em] text-subdued">
          Company
        </label>
        <input
          id="board-company"
          aria-label="Company"
          placeholder="Company name"
          value={company}
          onChange={(event) => setCompany(event.target.value)}
          className="mt-2 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent"
        />
      </div>
      <button
        type="submit"
        data-testid="create-source-board"
        disabled={!canSubmit}
        className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-background transition hover:bg-accent/90 disabled:opacity-50"
      >
        Add
      </button>
    </form>
  );
}

function BoardRow({ board }: { board: SourceBoard }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const mutation = useMutation({
    mutationFn: () => deleteSourceBoard(board.id),
    onSuccess: () => {
      toast("Source board removed.", "success");
      queryClient.invalidateQueries({ queryKey: ["source-boards"] });
    },
    onError: (error: Error) => toast(`Could not remove board: ${error.message}`)
  });

  return (
    <li
      data-testid="board-row"
      className="flex items-center justify-between gap-4 px-5 py-4"
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-text">{board.company_name}</span>
          <HealthBadge health={board.health} />
          <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-subdued">
            {board.source}
          </span>
        </div>
        <p className="mt-0.5 truncate font-mono text-[11px] text-subdued">{board.identifier}</p>
        <p className="mt-0.5 font-mono text-[11px] text-subdued">
          {board.last_success_at
            ? `Last success ${formatRelative(board.last_success_at)}`
            : "Never fetched successfully"}
          {board.consecutive_failures > 0 ? ` · ${board.consecutive_failures} failures in a row` : ""}
        </p>
      </div>
      <button
        type="button"
        data-testid={`delete-board-${board.id}`}
        onClick={() => mutation.mutate()}
        disabled={mutation.isPending}
        className="shrink-0 rounded-md border border-border px-3 py-1.5 text-xs text-subdued transition hover:border-red-500/50 hover:text-red-300 disabled:opacity-50"
      >
        Remove
      </button>
    </li>
  );
}

export default function SourceBoardsPage() {
  const { selectedUserId } = useDevUser();
  const query = useQuery({ queryKey: ["source-boards"], queryFn: listSourceBoards });
  const boards = query.data ?? [];

  return (
    <section className="space-y-6">
      <div>
        <Link href="/job-feed" className="font-mono text-xs text-subdued hover:text-text">
          ← Job Feed
        </Link>
        <p className="mt-3 font-mono text-xs uppercase tracking-[0.2em] text-accent">Settings</p>
        <h1 className="mt-3 text-3xl font-semibold text-text">Source boards</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-subdued">
          The company boards and feeds we watch for postings. A board that repeatedly fails degrades
          to <span className="text-yellow-300">degraded</span> and then{" "}
          <span className="text-red-300">dead</span> so we stop hammering it — re-verify or remove
          those.
        </p>
      </div>

      <NewBoardForm userId={selectedUserId} />

      {query.isLoading ? (
        <p className="text-sm text-subdued">Loading source boards…</p>
      ) : boards.length === 0 ? (
        <div className="rounded-xl border border-border bg-muted p-8">
          <h2 className="text-lg font-semibold text-text">No source boards yet</h2>
          <p className="mt-1 text-sm text-subdued">
            Add a Greenhouse board token, a Lever site, or an RSS feed URL to start ingesting
            postings.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-muted">
          {boards.map((board) => (
            <BoardRow key={board.id} board={board} />
          ))}
        </ul>
      )}
    </section>
  );
}
