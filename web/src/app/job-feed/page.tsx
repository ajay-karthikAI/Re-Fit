"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import { listSavedSearches, listSourceBoards } from "@/lib/api";
import { useDevUser } from "@/components/providers/dev-user-provider";
import { NewSearchForm } from "@/components/job-feed/new-search-form";
import { SavedSearchFeed } from "@/components/job-feed/saved-search-feed";

function EmptyState({ hasBoards }: { hasBoards: boolean }) {
  return (
    <div className="rounded-xl border border-border bg-muted p-8">
      <h2 className="text-lg font-semibold text-text">No saved searches yet</h2>
      {hasBoards ? (
        <p className="mt-1 text-sm text-subdued">
          Create a saved search above to start matching ingested postings against your profile.
        </p>
      ) : (
        <p className="mt-1 text-sm text-subdued">
          First, add the company boards you want to watch on the{" "}
          <Link href="/settings/source-boards" className="text-accent underline-offset-4 hover:underline">
            Source Boards
          </Link>{" "}
          settings page. Once postings are ingested, create a saved search to see matches here.
        </p>
      )}
    </div>
  );
}

export default function JobFeedPage() {
  const { selectedUserId } = useDevUser();
  const [showForm, setShowForm] = useState(false);
  const [activeSearchId, setActiveSearchId] = useState<string | null>(null);

  const searchesQuery = useQuery({
    queryKey: ["saved-searches", selectedUserId],
    queryFn: () => listSavedSearches(selectedUserId as string),
    enabled: selectedUserId !== null
  });

  const boardsQuery = useQuery({
    queryKey: ["source-boards"],
    queryFn: listSourceBoards
  });

  const searches = searchesQuery.data ?? [];
  const boards = boardsQuery.data ?? [];

  // Keep a valid selection as searches load or change.
  useEffect(() => {
    if (searches.length === 0) {
      setActiveSearchId(null);
      return;
    }
    if (!activeSearchId || !searches.some((search) => search.id === activeSearchId)) {
      setActiveSearchId(searches[0].id);
    }
  }, [searches, activeSearchId]);

  const activeSearch = searches.find((search) => search.id === activeSearchId) ?? null;

  return (
    <section className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-accent">Job Feed</p>
          <h1 className="mt-3 text-3xl font-semibold text-text">Matched postings</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-subdued">
            Postings from the boards you watch, scored against your profile. Generate a tailored kit
            in one click.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Link
            href="/settings/source-boards"
            className="rounded-md border border-border bg-surface px-4 py-2 text-sm text-text transition hover:border-accent"
          >
            Source boards
          </Link>
          <button
            type="button"
            onClick={() => setShowForm((value) => !value)}
            className="rounded-md border border-border bg-surface px-4 py-2 text-sm text-text transition hover:border-accent"
          >
            {showForm ? "Close" : "New search"}
          </button>
        </div>
      </div>

      {showForm && selectedUserId ? (
        <NewSearchForm
          userId={selectedUserId}
          onCreated={(search) => {
            setActiveSearchId(search.id);
            setShowForm(false);
          }}
        />
      ) : null}

      {searches.length > 0 ? (
        <div
          className="flex gap-1 overflow-x-auto border-b border-border pb-px"
          role="tablist"
          aria-label="Saved searches"
        >
          {searches.map((search) => {
            const active = search.id === activeSearchId;
            return (
              <button
                key={search.id}
                type="button"
                role="tab"
                aria-selected={active}
                data-testid={`search-tab-${search.id}`}
                onClick={() => setActiveSearchId(search.id)}
                className={[
                  "whitespace-nowrap rounded-t-md px-4 py-2 text-sm transition",
                  active
                    ? "border-b-2 border-accent text-text"
                    : "text-subdued hover:text-text"
                ].join(" ")}
              >
                {search.name}
              </button>
            );
          })}
        </div>
      ) : null}

      {searchesQuery.isLoading ? (
        <p className="text-sm text-subdued">Loading saved searches…</p>
      ) : activeSearch && selectedUserId ? (
        <SavedSearchFeed search={activeSearch} userId={selectedUserId} />
      ) : (
        <EmptyState hasBoards={boards.length > 0} />
      )}
    </section>
  );
}
