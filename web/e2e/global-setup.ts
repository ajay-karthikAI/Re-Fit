import { execSync } from "node:child_process";
import path from "node:path";

export default function globalSetup(): void {
  // Reseed the demo dashboard data (no LLM calls; needs Postgres + MinIO up).
  execSync("uv run python -m scripts.seed_dashboard", {
    cwd: path.resolve(__dirname, "../.."),
    stdio: "inherit",
    timeout: 180_000
  });
}
