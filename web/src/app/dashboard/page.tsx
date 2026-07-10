import { ApplicationsTable } from "@/components/dashboard/applications-table";
import { AurumDashboard } from "@/components/dashboard/aurum-dashboard";

export default function DashboardPage() {
  return (
    <div className="space-y-10">
      <AurumDashboard />
      <section className="space-y-4">
        <div>
          <p className="font-mono text-xs tracking-[0.14em] text-accent">APPLICATION TRACKER</p>
          <p className="mt-1.5 text-[13px] text-subdued">
            Every application records exactly which resume version went out — expand a row for
            the full kit.
          </p>
        </div>
        <ApplicationsTable />
      </section>
    </div>
  );
}
