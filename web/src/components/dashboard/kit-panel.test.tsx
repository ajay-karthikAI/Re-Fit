/**
 * Follow-up gating in the kit panel: generate buttons disable with a tooltip
 * until the application status permits the kind.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ApplicationListItem } from "@/lib/api";
import { KitPanel } from "@/components/dashboard/kit-panel";
import { ToastProvider } from "@/components/ui/toast";

const KIT = {
  application_id: "app-1",
  resume_version: {
    id: "rv-1",
    label: "Initech v1",
    template_id: "classic",
    created_at: "2026-07-01T00:00:00Z",
    score_before: 62.0,
    score_after: 81.0,
    missing_terms: ["Kafka"],
    pdf_url: "https://storage.example.test/resume.pdf",
    docx_url: null
  },
  cover_letter: null,
  followups: []
};

function application(overrides: Partial<ApplicationListItem>): ApplicationListItem {
  return {
    id: "app-1",
    user_id: "u-1",
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
    last_activity_at: "2026-07-01T00:00:00Z",
    ...overrides
  };
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input instanceof Request ? input.url : input);
      if (url.includes("/applications/app-1/kit")) {
        return new Response(JSON.stringify(KIT), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      throw new Error(`unmocked fetch: ${url}`);
    })
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderPanel(app: ApplicationListItem) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } }
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <KitPanel application={app} />
      </ToastProvider>
    </QueryClientProvider>
  );
}

describe("follow-up gating", () => {
  it("disables post-interview generation until status reaches interview", async () => {
    renderPanel(application({ status: "applied", applied_at: "2026-06-26T12:00:00Z" }));
    const button = await screen.findByRole("button", { name: "Generate post-interview" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Available once status reaches interview.");

    const postApply = screen.getByRole("button", { name: "Generate post-apply" });
    expect(postApply).toBeEnabled();
  });

  it("disables all generation without an applied date, with the scheduling reason", async () => {
    renderPanel(application({ status: "applied", applied_at: null }));
    const postApply = await screen.findByRole("button", { name: "Generate post-apply" });
    expect(postApply).toBeDisabled();
    expect(postApply).toHaveAttribute(
      "title",
      "Set the applied date first — it drives scheduling."
    );
  });

  it("enables post-interview once the status is interview", async () => {
    renderPanel(application({ status: "interview", applied_at: "2026-06-26T12:00:00Z" }));
    const button = await screen.findByRole("button", { name: "Generate post-interview" });
    expect(button).toBeEnabled();
    expect(button).not.toHaveAttribute("title");
  });

  it("shows the resume download URL from the kit", async () => {
    renderPanel(application({ status: "applied", applied_at: "2026-06-26T12:00:00Z" }));
    const link = await screen.findByTestId("download-pdf");
    expect(link).toHaveAttribute("href", "https://storage.example.test/resume.pdf");
  });
});
