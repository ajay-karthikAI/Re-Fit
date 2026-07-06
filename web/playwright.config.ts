import { defineConfig } from "@playwright/test";

/**
 * Smoke tests against the real stack: FastAPI must already be running on
 * :8100 with Postgres/MinIO up (`make up`, `make dev`). Global setup reseeds
 * the demo user via scripts/seed_dashboard.py.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: "http://localhost:3200",
    viewport: { width: 1440, height: 1000 },
    colorScheme: "dark"
  },
  webServer: {
    command: "corepack pnpm exec next dev --port 3200",
    url: "http://localhost:3200",
    // Never reuse: ports on this machine are shared with other local apps, so
    // reusing an existing server risks driving the wrong one.
    reuseExistingServer: false,
    timeout: 120_000
  }
});
