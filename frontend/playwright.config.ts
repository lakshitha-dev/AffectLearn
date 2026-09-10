import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for AffectLearn E2E tests.
 * Frontend: http://localhost:3000 (Next.js 16)
 * Backend API: http://localhost:8000
 */
export default defineConfig({
  testDir: "./e2e",
  outputDir: "test-results",

  /* Global timeout for each test */
  timeout: 30_000,

  /* Hard limit for the entire test suite */
  globalTimeout: 60_000 * 10, // 10 minutes total; per-test limit is above

  /* Retry once in CI to guard against flakiness */
  retries: process.env.CI ? 1 : 0,

  /* Parallelism — keep sequential inside each file so beforeAll state is shared */
  fullyParallel: false,
  workers: process.env.CI ? 1 : undefined,

  /* Reporters */
  reporter: [["list"], ["html", { open: "never" }]],

  use: {
    baseURL: "http://localhost:3000",

    /* Collect traces / screenshots on first retry */
    screenshot: "only-on-failure",
    video: "on-first-retry",
    trace: "on-first-retry",

    /* Extra HTTP headers for every request */
    extraHTTPHeaders: {
      Accept: "application/json",
    },
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  /* Start Next.js before running tests.
   *
   * Skipped when AL_BASE points somewhere other than localhost: the figure
   * captures in `figures-admin.spec.ts` run against a deployed instance while a
   * learner is using it, and booting a local server there would either fail or
   * capture the wrong system. */
  webServer: /^https?:\/\/localhost/.test(process.env.AL_BASE ?? "http://localhost:3000")
    ? {
        command: "pnpm start",
        url: "http://localhost:3000",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        stdout: "pipe",
        stderr: "pipe",
      }
    : undefined,
});
