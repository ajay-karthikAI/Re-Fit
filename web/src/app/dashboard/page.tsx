import { ApplicationsTable } from "@/components/dashboard/applications-table";

export default function DashboardPage() {
  return (
    <section className="space-y-6">
      <div>
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-accent">Dashboard</p>
        <h1 className="mt-3 text-3xl font-semibold text-text">Application tracker</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-subdued">
          Every application records exactly which resume version went out — expand a row to see
          the full kit: tailored resume, verified cover letter, and follow-ups.
        </p>
      </div>
      <ApplicationsTable />
    </section>
  );
}
