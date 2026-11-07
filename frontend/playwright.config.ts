import { defineConfig } from "@playwright/test";

/*
 * Needs the API in mock mode and the dashboard running (see README). Real spot prices must never reach
 * test output (AGENTS.md rule 6), so the suite refuses to run against real data.
 */
export default defineConfig({
  testDir: "tests/e2e",
  reporter: "line",
  workers: 1,
  timeout: 60_000,
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    channel: "msedge",
    viewport: { width: 1440, height: 900 },
    screenshot: "off",
    trace: "off",
  },
});
