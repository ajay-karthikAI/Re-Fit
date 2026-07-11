"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { type JobTargetCreate, createJobTarget, listJobTargets } from "@/lib/api";
import { useDevUser } from "@/components/providers/dev-user-provider";
import { useToast } from "@/components/ui/toast";

function NewJobTargetForm({ userId, onCreated }: { userId: string; onCreated: () => void }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [form, setForm] = useState<JobTargetCreate>({
    raw_description: "",
    company: "",
    title: "",
    source_url: ""
  });

  const mutation = useMutation({
    mutationFn: () =>
      createJobTarget(userId, {
        raw_description: form.raw_description,
        company: form.company || null,
        title: form.title || null,
        source_url: form.source_url || null
      }),
    onSuccess: () => {
      toast("Job target created.", "success");
      queryClient.invalidateQueries({ queryKey: ["job-targets", userId] });
      setForm({ raw_description: "", company: "", title: "", source_url: "" });
      onCreated();
    },
    onError: (error: Error) => toast(`Could not create job target: ${error.message}`)
  });

  return (
    <form
      className="space-y-3 rounded-lg border border-border bg-muted p-5"
      onSubmit={(event) => {
        event.preventDefault();
        if (form.raw_description.trim()) {
          mutation.mutate();
        }
      }}
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <input
          aria-label="Company"
          placeholder="Company (optional)"
          value={form.company ?? ""}
          onChange={(event) => setForm({ ...form, company: event.target.value })}
          className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent"
        />
        <input
          aria-label="Title"
          placeholder="Title (optional)"
          value={form.title ?? ""}
          onChange={(event) => setForm({ ...form, title: event.target.value })}
          className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent"
        />
        <input
          aria-label="Source URL"
          placeholder="URL (optional)"
          value={form.source_url ?? ""}
          onChange={(event) => setForm({ ...form, source_url: event.target.value })}
          className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent"
        />
      </div>
      <textarea
        aria-label="Job description"
        required
        placeholder="Paste the job description…"
        value={form.raw_description}
        onChange={(event) => setForm({ ...form, raw_description: event.target.value })}
        className="h-40 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent"
      />
      <button
        type="submit"
        data-testid="create-job-target"
        disabled={mutation.isPending || !form.raw_description.trim()}
        className="rounded-[10px] bg-gold-gradient px-4 py-2 text-sm font-bold text-onaccent transition enabled:hover:-translate-y-0.5 enabled:hover:shadow-gold disabled:opacity-50"
      >
        {mutation.isPending ? "Creating…" : "Create job target"}
      </button>
    </form>
  );
}

export default function JobTargetsPage() {
  const { selectedUserId } = useDevUser();
  const [showForm, setShowForm] = useState(false);

  const query = useQuery({
    queryKey: ["job-targets", selectedUserId],
    queryFn: () => listJobTargets(selectedUserId as string),
    enabled: selectedUserId !== null
  });

  const targets = query.data ?? [];

  return (
    <section className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-accent">Job Targets</p>
          <h1 className="mt-3 text-3xl font-semibold text-text">Job targets</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-subdued">
            Paste a job description, review the extracted requirements, and generate a tailored
            application kit.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowForm((value) => !value)}
          className="rounded-md border border-border bg-surface px-4 py-2 text-sm text-text transition hover:border-accent"
        >
          {showForm ? "Close" : "New job target"}
        </button>
      </div>

      {showForm && selectedUserId ? (
        <NewJobTargetForm userId={selectedUserId} onCreated={() => setShowForm(false)} />
      ) : null}

      {query.isLoading ? (
        <p className="text-sm text-subdued">Loading job targets…</p>
      ) : targets.length === 0 ? (
        <div className="rounded-lg border border-border bg-muted p-8">
          <h2 className="text-lg font-semibold text-text">No job targets yet</h2>
          <p className="mt-1 text-sm text-subdued">
            Add one to extract its requirements and generate a kit.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-muted">
          {targets.map((target) => (
            <li key={target.id}>
              <Link
                href={`/job-targets/${target.id}`}
                className="flex items-center justify-between gap-4 px-5 py-4 transition hover:bg-surface"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-text">
                    {target.company ?? "Untitled company"}
                    {target.title ? ` · ${target.title}` : ""}
                  </p>
                  <p className="mt-0.5 font-mono text-[11px] text-subdued">
                    {new Date(target.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span
                    className={[
                      "rounded border px-1.5 py-0.5 font-mono text-[11px]",
                      target.has_requirements
                        ? "border-accent/40 text-accent"
                        : "border-dashed border-border text-subdued"
                    ].join(" ")}
                  >
                    reqs
                  </span>
                  <span
                    className={[
                      "rounded border px-1.5 py-0.5 font-mono text-[11px]",
                      target.has_kit
                        ? "border-accent/40 text-accent"
                        : "border-dashed border-border text-subdued"
                    ].join(" ")}
                  >
                    kit
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
