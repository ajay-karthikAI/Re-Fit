import { execSync } from "node:child_process";
import path from "node:path";

import { expect, test } from "@playwright/test";

// Seed a fully-cached Greenhouse apply kit (no LLM at request time) and capture
// the ids it prints.
let seeded: { user_id: string; job_target_id: string };

test.beforeAll(() => {
  const output = execSync("uv run python -m scripts.seed_apply_kit", {
    cwd: path.resolve(__dirname, "../.."),
    encoding: "utf8",
    timeout: 180_000
  });
  seeded = JSON.parse(output.slice(output.indexOf("{")));
});

test("apply kit: copy every field, why_company lands as plain text", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.addInitScript((id) => {
    window.localStorage.setItem("refit.devUserId", id);
  }, seeded.user_id);

  await page.goto(`/job-targets/${seeded.job_target_id}`);
  await page.getByTestId("tab-apply").click();

  const kit = page.getByTestId("apply-kit");
  await expect(kit).toBeVisible({ timeout: 60_000 });

  // Documents pinned near the top.
  await expect(page.getByTestId("document-resume_pdf")).toBeVisible();
  await expect(page.getByTestId("document-cover_letter_pdf")).toBeVisible();
  // The blank referral source surfaces as a gap.
  await expect(page.getByTestId("gap-referral_source_default")).toBeVisible();

  // Copy every copyable field via the UI.
  const copyButtons = page.locator('[data-testid^="copy-"]');
  const count = await copyButtons.count();
  expect(count).toBeGreaterThan(0);
  for (let i = 0; i < count; i += 1) {
    await copyButtons.nth(i).click();
  }

  // The why_company primary button copies plain text (markdown stripped).
  await page.getByTestId("copy-why_company").click();
  const clipboard = await page.evaluate(() => navigator.clipboard.readText());
  expect(clipboard).toContain("retrieval-augmented generation pipeline serving 40k queries/day");
  expect(clipboard).not.toContain("**");

  await page.screenshot({ path: "e2e/artifacts/apply-kit.png", fullPage: true });
});
