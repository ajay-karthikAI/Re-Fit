"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { PlanCard } from "@/components/dashboard/aurum-dashboard";
import { UserPicker } from "@/components/shell/user-picker";

const navItems = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/job-feed", label: "Job Feed" },
  { href: "/job-targets", label: "Job Targets" },
  { href: "/versions", label: "Versions" },
  { href: "/profile", label: "Profile" }
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-background text-text">
      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col gap-7 border-r border-accent/10 px-4 py-6 lg:flex">
        <Link href="/dashboard" className="flex items-center gap-2.5 px-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-[7px] bg-gold-mark text-[15px] font-bold text-background">
            R
          </span>
          <span>
            <span className="block text-base font-bold tracking-[0.04em]">RE-FIT</span>
            <span className="block font-mono text-[10.5px] text-faint">APPLICATION KITS</span>
          </span>
        </Link>
        <nav className="grid gap-1">
          {navItems.map((item, index) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={[
                  "flex items-center gap-3 rounded-[10px] border px-3 py-2.5 text-sm font-medium transition",
                  active
                    ? "border-accent/30 bg-accent/[0.08] text-accent"
                    : "border-transparent text-subdued hover:bg-accent/[0.08] hover:text-accent"
                ].join(" ")}
              >
                <span
                  className={[
                    "font-mono text-[11px]",
                    active ? "text-accent" : "text-faint"
                  ].join(" ")}
                >
                  {String(index + 1).padStart(2, "0")}
                </span>
                {item.label}
              </Link>
            );
          })}
        </nav>
        <PlanCard />
      </aside>

      <div className="lg:pl-60">
        <header className="sticky top-0 z-10 border-b border-accent/10 bg-background/95 px-5 py-4 backdrop-blur lg:px-8">
          <div className="flex items-center justify-between gap-4">
            <nav className="flex gap-1 overflow-x-auto lg:hidden">
              {navItems.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={[
                      "whitespace-nowrap rounded-[10px] border px-3 py-2 text-sm",
                      active
                        ? "border-accent/30 bg-accent/[0.08] text-accent"
                        : "border-transparent text-subdued"
                    ].join(" ")}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
            <div className="hidden min-w-0 lg:block">
              <p className="font-mono text-xs text-faint">localhost workspace</p>
            </div>
            <UserPicker />
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1160px] px-5 py-8 lg:px-9 lg:py-10">{children}</main>
      </div>
    </div>
  );
}
