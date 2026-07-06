import { expect, test } from "@playwright/test";

test("dashboard renders the seeded application and exposes the kit", async ({ page }) => {
  await page.goto("/dashboard");

  // Use the seeded demo user.
  await page.getByLabel("Dev user").selectOption({ label: "demo@refit.local" });

  // The seeded applied application renders with its exact resume version label.
  const row = page.getByTestId("application-row").filter({ hasText: "Anthropic" });
  await expect(row).toBeVisible();
  await expect(row).toContainText("Anthropic Applied AI v1");
  await expect(row).toContainText("Applied");

  // Status counts render as filter chips.
  await expect(page.getByTestId("status-chips")).toContainText("Applied 1");
  await expect(page.getByTestId("status-chips")).toContainText("Draft 1");

  // Expand the row: the kit view shows resume version, cover letter, follow-ups.
  await row.getByRole("button", { name: "Expand kit" }).click();
  const kit = page.getByTestId("kit-panel");
  await expect(kit).toBeVisible();
  await expect(kit).toContainText("Resume version");
  await expect(kit).toContainText("claims verified");
  await expect(kit).toContainText("Post-apply");

  // The resume download button holds a presigned URL.
  const download = kit.getByTestId("download-pdf");
  await expect(download).toBeVisible();
  const href = await download.getAttribute("href");
  expect(href).toBeTruthy();
  expect(href).toContain("http");

  await page.screenshot({ path: "e2e/artifacts/dashboard-expanded.png", fullPage: true });
});
