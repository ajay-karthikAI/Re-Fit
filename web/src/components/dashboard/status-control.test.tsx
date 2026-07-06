/**
 * Status pipeline behavior at the table level: optimistic flip on PATCH,
 * rollback + toast when the backend returns 500.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApplicationsTable } from "@/components/dashboard/applications-table";
import { DevUserProvider } from "@/components/providers/dev-user-provider";
import { ToastProvider } from "@/components/ui/toast";

const USER = {
  id: "u-1",
  email: "demo@refit.local",
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z"
};

const APPLICATION = {
  id: "app-1",
  user_id: USER.id,
  job_target_id: "jt-1",
  resume_version_id: "rv-1",
  status: "draft",
  applied_at: null,
  notes: null,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
  company: "Initech",
  title: "Staff Engineer",
  resume_version_label: "Initech v1",
  ats_score: 81.0,
  resume_pdf_ready: true,
  has_cover_letter: true,
  followup_count: 0,
  last_activity_at: "2026-07-01T00:00:00Z"
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

let patchStatus: number;
let patchCalls: number;

beforeEach(() => {
  patchStatus = 200;
  patchCalls = 0;
  window.localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input instanceof Request ? input.url : input);
      const method = (input instanceof Request ? input.method : init?.method) ?? "GET";
      if (url.endsWith("/users") && method === "GET") {
        return jsonResponse([USER]);
      }
      if (url.includes(`/users/${USER.id}/applications`) && method === "GET") {
        return jsonResponse([APPLICATION]);
      }
      if (url.includes("/applications/app-1") && method === "PATCH") {
        patchCalls += 1;
        // Small delay so tests can observe the optimistic state before settle.
        await new Promise((resolve) => setTimeout(resolve, 50));
        if (patchStatus >= 400) {
          return jsonResponse({ detail: "backend exploded" }, patchStatus);
        }
        return jsonResponse({ ...APPLICATION, status: "applied" });
      }
      throw new Error(`unmocked fetch: ${method} ${url}`);
    })
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderTable() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } }
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <DevUserProvider>
          <ApplicationsTable />
        </DevUserProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}

async function markApplied(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("radio", { name: "Applied" }));
  await user.click(screen.getByRole("button", { name: "Mark applied" }));
}

describe("StatusControl in the applications table", () => {
  it("optimistically flips the status and keeps it on success", async () => {
    const user = userEvent.setup();
    renderTable();
    expect(await screen.findByRole("radio", { name: "Draft" })).toBeChecked();

    await markApplied(user);

    // Optimistic: checked immediately, before/without refetch settling.
    expect(screen.getByRole("radio", { name: "Applied" })).toBeChecked();
    await waitFor(() => expect(patchCalls).toBe(1));
    expect(screen.getByRole("radio", { name: "Applied" })).toBeChecked();
  });

  it("rolls back the optimistic flip and shows a toast when PATCH returns 500", async () => {
    patchStatus = 500;
    const user = userEvent.setup();
    renderTable();
    expect(await screen.findByRole("radio", { name: "Draft" })).toBeChecked();

    await markApplied(user);

    // Optimistic flip happens first...
    expect(screen.getByRole("radio", { name: "Applied" })).toBeChecked();

    // ...then the failure rolls it back and surfaces a toast.
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "Draft" })).toBeChecked()
    );
    expect(screen.getByRole("status")).toHaveTextContent(/Status update failed/);
  });
});
