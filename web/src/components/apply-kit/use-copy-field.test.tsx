/**
 * useCopyField via FieldRow: the clipboard must receive plain text (markdown
 * stripped) for the "Copy as plain text" action on a generated answer, the raw
 * markdown for "Copy markdown", and the literal value for a simple field.
 *
 * We drive clicks with fireEvent (not userEvent) so our navigator.clipboard spy
 * is the one exercised — userEvent.setup installs its own clipboard stub.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ApplyKitField } from "@/lib/api";
import { FieldRow } from "@/components/apply-kit/field-row";
import { ToastProvider } from "@/components/ui/toast";

const PROSE_MARKDOWN =
  "At **Nimbus Freight** I built Python APIs.\n\n- shipped fast\n- *measured* everything";
const PROSE_PLAIN = "At Nimbus Freight I built Python APIs.\n\nshipped fast\nmeasured everything";

function proseField(): ApplyKitField {
  return {
    field_spec: {
      key: "why_company",
      label: "Why do you want to work here?",
      source: "generated",
      mapped_from: null,
      question_kind: "why_company",
      notes: null
    },
    resolved_value: PROSE_MARKDOWN,
    status: "ready",
    error: null
  };
}

function simpleField(): ApplyKitField {
  return {
    field_spec: {
      key: "email",
      label: "Email",
      source: "profile",
      mapped_from: "profile.contact.email",
      question_kind: null,
      notes: null
    },
    resolved_value: "sam@example.com",
    status: "ready",
    error: null
  };
}

let writeText: ReturnType<typeof vi.fn>;

beforeEach(() => {
  writeText = vi.fn(async () => undefined);
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function renderField(field: ApplyKitField) {
  return render(
    <ToastProvider>
      <FieldRow field={field} />
    </ToastProvider>
  );
}

describe("useCopyField in FieldRow", () => {
  it("copies markdown stripped to plain text for a generated answer", async () => {
    renderField(proseField());

    fireEvent.click(screen.getByTestId("copy-why_company"));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText).toHaveBeenCalledWith(PROSE_PLAIN);
    expect(writeText.mock.calls[0][0]).not.toContain("**");
  });

  it("copies the raw markdown when the markdown button is used", async () => {
    renderField(proseField());

    fireEvent.click(screen.getByTestId("copy-why_company-md"));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(PROSE_MARKDOWN));
  });

  it("copies the literal value for a simple field", async () => {
    renderField(simpleField());

    fireEvent.click(screen.getByTestId("copy-email"));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("sam@example.com"));
  });

  it("shows the copied checkmark and toast after copying", async () => {
    renderField(simpleField());

    const button = screen.getByTestId("copy-email");
    fireEvent.click(button);
    await waitFor(() => expect(button).toHaveTextContent("Copied"));
    expect(screen.getByRole("status")).toHaveTextContent("Copied ✓");
  });
});
