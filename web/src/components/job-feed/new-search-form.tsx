"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { type SavedSearch, createSavedSearch, getProfile } from "@/lib/api";
import { MinScoreSlider } from "@/components/job-feed/min-score-slider";
import { useToast } from "@/components/ui/toast";

function toList(value: string): string[] | undefined {
  const items = value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length > 0 ? items : undefined;
}

export function NewSearchForm({
  userId,
  onCreated
}: {
  userId: string;
  onCreated: (search: SavedSearch) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [name, setName] = useState("");
  const [minScore, setMinScore] = useState(75);
  const [locations, setLocations] = useState("");
  const [departments, setDepartments] = useState("");

  // One canonical profile per user today; the picker future-proofs the "profile
  // version" the search scores against.
  const profileQuery = useQuery({
    queryKey: ["profile", userId],
    queryFn: () => getProfile(userId)
  });
  const profile = profileQuery.data ?? null;

  const mutation = useMutation({
    mutationFn: () => {
      if (!profile) {
        throw new Error("Build your profile before creating a saved search.");
      }
      const filters =
        toList(locations) || toList(departments)
          ? { locations: toList(locations) ?? null, departments: toList(departments) ?? null }
          : null;
      return createSavedSearch({
        user_id: userId,
        name: name.trim(),
        profile_id: profile.id,
        min_score: minScore,
        filters
      });
    },
    onSuccess: (search) => {
      toast("Saved search created.", "success");
      queryClient.invalidateQueries({ queryKey: ["saved-searches", userId] });
      onCreated(search);
    },
    onError: (error: Error) => toast(error.message)
  });

  const canSubmit = Boolean(profile) && name.trim().length > 0 && !mutation.isPending;

  return (
    <form
      className="space-y-4 rounded-xl border border-border bg-muted p-5"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit) {
          mutation.mutate();
        }
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label
            htmlFor="search-name"
            className="font-mono text-xs uppercase tracking-[0.16em] text-subdued"
          >
            Name
          </label>
          <input
            id="search-name"
            aria-label="Search name"
            placeholder="e.g. Senior ML roles"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="mt-2 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent"
          />
        </div>
        <div>
          <label
            htmlFor="search-profile"
            className="font-mono text-xs uppercase tracking-[0.16em] text-subdued"
          >
            Profile version
          </label>
          <select
            id="search-profile"
            aria-label="Profile version"
            disabled={!profile}
            className="mt-2 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent disabled:opacity-50"
          >
            {profile ? (
              <option value={profile.id}>Canonical profile</option>
            ) : (
              <option>No profile yet — build one first</option>
            )}
          </select>
        </div>
      </div>

      <MinScoreSlider value={minScore} onChange={setMinScore} label="Minimum match score" />

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label
            htmlFor="search-locations"
            className="font-mono text-xs uppercase tracking-[0.16em] text-subdued"
          >
            Locations (optional)
          </label>
          <input
            id="search-locations"
            aria-label="Locations"
            placeholder="Remote, San Francisco"
            value={locations}
            onChange={(event) => setLocations(event.target.value)}
            className="mt-2 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent"
          />
        </div>
        <div>
          <label
            htmlFor="search-departments"
            className="font-mono text-xs uppercase tracking-[0.16em] text-subdued"
          >
            Departments (optional)
          </label>
          <input
            id="search-departments"
            aria-label="Departments"
            placeholder="Engineering, Research"
            value={departments}
            onChange={(event) => setDepartments(event.target.value)}
            className="mt-2 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent"
          />
        </div>
      </div>

      <button
        type="submit"
        data-testid="create-saved-search"
        disabled={!canSubmit}
        className="rounded-[10px] bg-gold-gradient px-4 py-2 text-sm font-bold text-onaccent transition enabled:hover:-translate-y-0.5 enabled:hover:shadow-gold disabled:opacity-50"
      >
        {mutation.isPending ? "Creating…" : "Create saved search"}
      </button>
    </form>
  );
}
