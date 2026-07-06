import path from "node:path";

import { expect, test } from "@playwright/test";

const API = "http://localhost:8100";
const FIXTURE_RESUME = path.resolve(
  __dirname,
  "../../tests/corpus/resumes/synthetic_two_column.pdf"
);

const JD = `Senior Backend Engineer

We need a backend engineer strong in Python and PostgreSQL to build and operate
production services on AWS. Experience with FastAPI, distributed systems, and
observability is required. Kafka and Kubernetes are a plus.`;

// Phase 2 exit criterion as a test: upload a resume, create a job target,
// generate the kit, track the application, and confirm the dashboard shows the
// kit attached to that application. Real LLM calls (parse + tailor + letter),
// so this is deliberately slow.
test("phase 2 exit: upload → job target → generate kit → track → dashboard", async ({
  page,
  request
}) => {
  test.setTimeout(300_000);

  // Fresh user so the run is isolated from seeded demo data.
  // .local is rejected by EmailStr at the API boundary; use a real-looking TLD.
  const email = `e2e-phase2-${Date.now()}@example.com`;
  const userResponse = await request.post(`${API}/users`, { data: { email } });
  expect(userResponse.ok()).toBeTruthy();
  const userId = (await userResponse.json()).id as string;

  // Select this user before the app boots.
  await page.addInitScript((id) => {
    window.localStorage.setItem("refit.devUserId", id);
  }, userId);

  // 1. Upload + parse the resume into the canonical profile.
  await page.goto("/profile");
  await page.getByTestId("resume-upload").setInputFiles(FIXTURE_RESUME);
  await expect(page.getByTestId("save-profile")).toBeVisible({ timeout: 120_000 });

  // 2. Create a job target.
  await page.goto("/job-targets");
  await page.getByRole("button", { name: "New job target" }).click();
  await page.getByLabel("Company").fill("Northwind");
  await page.getByLabel("Title").fill("Senior Backend Engineer");
  await page.getByLabel("Job description").fill(JD);
  await page.getByTestId("create-job-target").click();

  // 3. Open the job target and generate the kit.
  await page.getByRole("link", { name: /Northwind/ }).click();
  await expect(page.getByTestId("generate-kit")).toBeVisible();
  await page.getByTestId("generate-kit").click();

  // The money moment: the score count-up appears and finishes animating.
  const scoreValue = page.getByTestId("score-value");
  await expect(scoreValue).toBeVisible({ timeout: 240_000 });
  await expect(scoreValue).toHaveAttribute("data-landed", "true", { timeout: 5_000 });
  await page.screenshot({ path: "e2e/artifacts/kit-generated.png", fullPage: true });

  // 4. Track the application → deep-link to the dashboard row.
  await page.getByTestId("track-application").click();
  await page.waitForURL(/\/dashboard\?application=/, { timeout: 30_000 });

  // 5. Dashboard shows the application with the kit attached (auto-expanded).
  const row = page.getByTestId("application-row").filter({ hasText: "Northwind" });
  await expect(row).toBeVisible();
  const kit = page.getByTestId("kit-panel");
  await expect(kit).toBeVisible({ timeout: 20_000 });
  await expect(kit).toContainText("Resume version");
  await expect(kit).toContainText("claims verified");
});
