"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { AppShell } from "@/components/shell/app-shell";
import { DevUserProvider } from "@/components/providers/dev-user-provider";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { ToastProvider } from "@/components/ui/toast";

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: 1,
            staleTime: 20_000
          }
        }
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ToastProvider>
          <DevUserProvider>
            <AppShell>{children}</AppShell>
          </DevUserProvider>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
