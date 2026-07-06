"use client";

import { useQuery } from "@tanstack/react-query";

import { getHealth } from "@/lib/api";

function StatusPill({ label, value }: { label: string; value?: string }) {
  const ok = value === "ok";
  return (
    <div className="rounded-md border border-border bg-surface p-4">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-subdued">{label}</p>
      <p className={["mt-3 text-2xl font-semibold", ok ? "text-accent" : "text-text"].join(" ")}>
        {value ?? "unknown"}
      </p>
    </div>
  );
}

export function HealthPanel() {
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 30_000
  });

  return (
    <div className="rounded-lg border border-border bg-muted p-5 shadow-panel">
      <div className="flex flex-col gap-2 border-b border-border pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-text">Backend health</h2>
          <p className="mt-1 text-sm text-subdued">
            Loaded from FastAPI through the generated OpenAPI client.
          </p>
        </div>
        <span className="font-mono text-xs text-subdued">
          {healthQuery.isFetching ? "refreshing" : "typed fetch"}
        </span>
      </div>

      {healthQuery.error ? (
        <div className="mt-4 rounded-md border border-red-500/40 bg-red-950/20 p-4 text-sm text-red-200">
          Could not reach FastAPI at the configured base URL.
        </div>
      ) : (
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <StatusPill label="API" value={healthQuery.data?.status} />
          <StatusPill label="Postgres" value={healthQuery.data?.postgres} />
          <StatusPill label="Redis" value={healthQuery.data?.redis} />
        </div>
      )}
    </div>
  );
}
