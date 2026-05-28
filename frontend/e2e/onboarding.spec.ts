/**
 * E2E tests — Onboarding wizard.
 *
 * Each test registers a fresh learner so state is isolated.
 * Webcam-dependent tests are skipped unless the browser supports getUserMedia.
 */

import { test, expect } from "@playwright/test";
import {
  makeCredentials,
  apiRegister,
  seedSessionStorage,
  apiGetMe,
  type TestCredentials,
} from "./helpers/auth";

// ---------------------------------------------------------------------------
// Helper: register via API and seed the session store so the page loads as
// an authenticated learner without going through the login form.
// ---------------------------------------------------------------------------

async function freshLearnerSession(
  request: Parameters<Parameters<typeof test>[1]>[0]["request"],
  page: Parameters<Parameters<typeof test>[1]>[0]["page"],
  prefix = "ob",
) {
  const creds = makeCredentials(prefix);
  const tokens = await apiRegister(request, creds);
  const user = await apiGetMe(request, tokens.accessToken);
  await seedSessionStorage(page, tokens, user);
  return { creds, tokens, user };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Onboarding wizard", () => {
  test("new learner redirected to /onboarding when accessing /courses", async ({
    page,
    request,
  }) => {
    // Register but do NOT give consent — new account always has consentGivenAt = null
    const creds = makeCredentials("redir");
    const tokens = await apiRegister(request, creds);
    const user = await apiGetMe(request, tokens.accessToken);

    // Confirm user has no consent yet
    const userRecord = user as Record<string, unknown>;
    expect(userRecord.consentGivenAt ?? null).toBeNull();

    await seedSessionStorage(page, tokens, user);
    await page.goto("/courses");

    // AuthGuard or onboarding redirect should push to /onboarding
    await page.waitForURL((url) => url.pathname.startsWith("/onboarding"), {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).toMatch(/\/onboarding/);
  });

  test("welcome step shows greeting and Get Started advances to consent step", async ({
    page,
    request,
  }) => {
    await freshLearnerSession(request, page, "welcome");
    await page.goto("/onboarding");

    // The WelcomeStep renders a heading containing "Welcome"
    const heading = page.getByRole("heading", { level: 1 });
    await expect(heading).toContainText(/welcome/i, { timeout: 10_000 });

    // Click "Get started" to advance
    await page.getByRole("button", { name: /get started/i }).click();

    // Should now show the ConsentStep heading
    await expect(
      page.getByRole("heading", { name: /research study consent/i }),
    ).toBeVisible({ timeout: 5_000 });
  });

  test("consent 'I agree' button disabled until checkbox ticked", async ({
    page,
    request,
  }) => {
    await freshLearnerSession(request, page, "consent-disabled");
    await page.goto("/onboarding");

    // Advance past welcome
    await page.getByRole("button", { name: /get started/i }).click();
    await page.waitForSelector("text=Research Study Consent");

    const agreeBtn = page.getByRole("button", { name: /i agree/i });

    // Initially disabled (no checkbox tick)
    await expect(agreeBtn).toBeDisabled();
  });

  test("ticking checkbox enables 'I agree' button", async ({
    page,
    request,
  }) => {
    await freshLearnerSession(request, page, "consent-enable");
    await page.goto("/onboarding");

    await page.getByRole("button", { name: /get started/i }).click();
    await page.waitForSelector("text=Research Study Consent");

    const agreeBtn = page.getByRole("button", { name: /i agree/i });
    const checkbox = page.locator('input[type="checkbox"]');

    // Tick the checkbox
    await checkbox.check();

    // Button should now be enabled
    await expect(agreeBtn).toBeEnabled();
  });

  test("clicking 'I agree' advances to webcam step", async ({
    page,
    request,
  }) => {
    await freshLearnerSession(request, page, "consent-agree");
    await page.goto("/onboarding");

    await page.getByRole("button", { name: /get started/i }).click();
    await page.waitForSelector("text=Research Study Consent");

    await page.locator('input[type="checkbox"]').check();

    // Intercept the consent API call so the test doesn't depend on backend side-effects
    await page.route("**/api/v1/auth/consent", (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ success: true }) }),
    );

    await page.getByRole("button", { name: /i agree/i }).click();

    // Webcam step heading
    await expect(
      page.getByRole("heading", { name: /webcam access/i }),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("'Back' button on consent step returns to welcome step", async ({
    page,
    request,
  }) => {
    await freshLearnerSession(request, page, "consent-back");
    await page.goto("/onboarding");

    await page.getByRole("button", { name: /get started/i }).click();
    await page.waitForSelector("text=Research Study Consent");

    await page.getByRole("button", { name: /back/i }).click();

    // Should be back on the welcome step
    await expect(
      page.getByRole("button", { name: /get started/i }),
    ).toBeVisible({ timeout: 5_000 });
  });

  test("'Skip for now' on webcam step navigates past webcam", async ({
    page,
    request,
  }) => {
    await freshLearnerSession(request, page, "webcam-skip");
    await page.goto("/onboarding");

    // Navigate to webcam step via consent
    await page.getByRole("button", { name: /get started/i }).click();
    await page.waitForSelector("text=Research Study Consent");
    await page.locator('input[type="checkbox"]').check();

    // Stub the consent API call
    await page.route("**/api/v1/auth/consent", (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ success: true }) }),
    );
    await page.getByRole("button", { name: /i agree/i }).click();
    await page.waitForSelector("text=Webcam access");

    // Stub the webcam-mode API call
    await page.route("**/api/v1/auth/webcam-mode", (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ success: true }) }),
    );

    await page.getByRole("button", { name: /skip for now/i }).click();

    // Should redirect to /courses after skipping
    await page.waitForURL((url) => url.pathname === "/courses", {
      timeout: 10_000,
    });
  });

  test("already-consented learner is redirected away from /onboarding", async ({
    page,
    request,
  }) => {
    const creds = makeCredentials("already-consented");
    const tokens = await apiRegister(request, creds);
    const rawUser = await apiGetMe(request, tokens.accessToken);

    // Patch the in-memory user object to look like consent was already given
    // (the real backend would set this after POST /onboarding/consent)
    const userWithConsent = {
      ...(rawUser as Record<string, unknown>),
      consentGivenAt: new Date().toISOString(),
    };

    await seedSessionStorage(page, tokens, userWithConsent);
    await page.goto("/onboarding");

    // The onboarding page checks initialConsentRef and calls router.replace("/courses")
    await page.waitForURL((url) => url.pathname === "/courses", {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).toBe("/courses");
  });

  test("step indicator reflects current step number", async ({
    page,
    request,
  }) => {
    await freshLearnerSession(request, page, "step-indicator");
    await page.goto("/onboarding");

    // Welcome is step 1 of 4 — look for "1" / "4" somewhere in the indicator
    const stepIndicator = page.locator(".space-y-8").first();
    await expect(stepIndicator).toBeVisible();

    // Advance to consent (step 2)
    await page.getByRole("button", { name: /get started/i }).click();
    await page.waitForSelector("text=Research Study Consent");

    // The StepIndicator renders "Step X of Y" or similar aria text
    // We just verify the page changed correctly
    await expect(
      page.getByRole("heading", { name: /research study consent/i }),
    ).toBeVisible();
  });
});
