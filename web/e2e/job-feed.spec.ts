import { execSync } from "node:child_process";
import path from "node:path";

import { expect, test } from "@playwright/test";

// Seed a job feed with a fully-cached kit behind the first posting (no LLM at
// request time), and capture the ids it prints.
let seeded: {
  user_id: string;
  saved_search_id: string;
  kitted_posting_id: string;
  kitted_posting_title: string;
};

test.beforeAll(() => {
  const output = execSync("uv run python -m scripts.seed_job_feed", {
    cwd: path.resolve(__dirname, "../.."),
    encoding: "utf8",
    timeout: 300_000
  });
  seeded = JSON.parse(output.slice(output.indexOf("{")));
});

// Phase 4 exit criterion as a test: from the Job Feed, one click on a matched
// posting lands on the kit view with resume + cover letter both ready.
test("job feed: Generate kit on a posting → land on the ready kit view", async ({ page }) => {
  test.setTimeout(120_000);

  await page.addInitScript((id) => {
    window.localStorage.setItem("refit.devUserId", id);
  }, seeded.user_id);

  await page.goto("/job-feed");

  // The saved search's matches render as posting cards.
  await expect(page.getByTestId("posting-list")).toBeVisible({ timeout: 30_000 });
  const generate = page.getByTestId(`generate-kit-${seeded.kitted_posting_id}`);
  await expect(generate).toBeVisible();

  await page.screenshot({ path: "e2e/artifacts/job-feed.png", fullPage: true });

  // THE one click.
  await generate.click();

  // Lands on the kit view for the freshly-materialised job target.
  await page.waitForURL(/\/job-targets\/[0-9a-f-]+$/, { timeout: 60_000 });

  const kit = page.getByTestId("kit-result");
  await expect(kit).toBeVisible({ timeout: 60_000 });

  // Resume + cover letter both ready.
  await expect(page.getByRole("link", { name: "Download resume PDF" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download cover letter PDF" })).toBeVisible();

  // The money moment: the ATS score has landed.
  const scoreValue = page.getByTestId("score-value");
  await expect(scoreValue).toBeVisible();
  await expect(scoreValue).toHaveAttribute("data-landed", "true", { timeout: 5_000 });

  await page.screenshot({ path: "e2e/artifacts/job-feed-kit.png", fullPage: true });
});
