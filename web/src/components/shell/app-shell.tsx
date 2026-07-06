"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { UserPicker } from "@/components/shell/user-picker";

const navItems = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/job-targets", label: "Job Targets" },
  { href: "/versions", label: "Versions" },
  { href: "/profile", label: "Profile" }
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-background text-text">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-border bg-surface px-5 py-6 lg:block">
        <Link href="/dashboard" className="block">
          <span className="font-mono text-xs uppercase tracking-[0.22em] text-accent">Re-Fit</span>
          <span className="mt-3 block text-xl font-semibold">Application kits</span>
        </Link>
        <nav className="mt-10 space-y-1">
          {navItems.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={[
                  "block rounded-md px-3 py-2 text-sm transition",
                  active
                    ? "bg-muted text-text"
                    : "text-subdued hover:bg-muted/70 hover:text-text"
                ].join(" ")}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-10 border-b border-border bg-background/95 px-5 py-4 backdrop-blur lg:px-8">
          <div className="flex items-center justify-between gap-4">
            <nav className="flex gap-1 overflow-x-auto lg:hidden">
              {navItems.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={[
                      "whitespace-nowrap rounded-md px-3 py-2 text-sm",
                      active ? "bg-muted text-text" : "text-subdued"
                    ].join(" ")}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
            <div className="hidden min-w-0 lg:block">
              <p className="font-mono text-xs text-subdued">localhost workspace</p>
            </div>
            <UserPicker />
          </div>
        </header>

        <main className="mx-auto w-full max-w-6xl px-5 py-8 lg:px-8 lg:py-10">{children}</main>
      </div>
    </div>
  );
}
