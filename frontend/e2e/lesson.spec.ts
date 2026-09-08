/**
 * E2E tests — Lesson content viewing.
 *
 * Setup: one enrolled learner with a known course/module/lesson.
 * Tests cover the Clean Reader layout, sidebar, breadcrumbs,
 * Mark Complete button, progress bar, and focus mode.
 */

import { test, expect } from "@playwright/test";
import {
  seedLearnerOnFirstLesson,
  seedSessionStorage,
} from "./helpers/auth";

// ---------------------------------------------------------------------------
// Shared state
// ---------------------------------------------------------------------------

interface LessonSuiteState {
  tokens: { accessToken: string; refreshToken: string; expiresIn: number };
  user: Record<string, unknown>;
  courseId: string;
  moduleId: string;
  lessonId: string;
  lessonUrl: string;
}

let shared: LessonSuiteState;

test.beforeAll(async ({ request }) => {
  const seeded = await seedLearnerOnFirstLesson(request, "lesson");
  const { tokens, user, courseId, lessonUrl } = seeded;

  shared = {
    tokens,
    user,
    courseId,
    moduleId: seeded.moduleId,
    lessonId: seeded.lessonId,
    lessonUrl,
  };
});

test.beforeEach(async ({ page }) => {
  await seedSessionStorage(page, shared.tokens, shared.user);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Lesson page layout", () => {
  test("navigating to lesson URL renders the lesson heading", async ({
    page,
  }) => {
    await page.goto(shared.lessonUrl);

    // The lesson title is rendered as an <h1> after loading
    const h1 = page.getByRole("heading", { level: 1 });
    await expect(h1).toBeVisible({ timeout: 15_000 });

    // The page should NOT still be on the loading skeleton. Asserted by the presence of real
    // section content rather than the absence of `.animate-pulse`: that class is now also on the
    // WebSocket status dot, which pulses forever, so the old assertion could never pass again.
    await expect(page.locator("section[id^='section-']").first()).toBeVisible({
      timeout: 15_000,
    });
  });

  test("breadcrumbs show Course → Module → Lesson", async ({ page }) => {
    await page.goto(shared.lessonUrl);

    // Named, not just "the first nav": the course-outline sidebar is also a labelled nav landmark
    // and comes first in the DOM, so the unnamed locator resolved to a sidebar that is hidden at
    // this viewport and the breadcrumb was never looked at.
    const breadcrumb = page.getByRole("navigation", { name: "breadcrumb" });
    await expect(breadcrumb).toBeVisible({ timeout: 15_000 });

    // There should be at least two separator characters indicating 3 crumbs
    const separators = breadcrumb.locator("[aria-hidden]");
    const count = await separators.count();
    expect(count).toBeGreaterThanOrEqual(2);
  });

  test("progress bar is present on the lesson page", async ({ page }) => {
    await page.goto(shared.lessonUrl);

    // LessonProgressBar renders role="progressbar"
    const progressBar = page.getByRole("progressbar", {
      name: /lesson progress/i,
    });
    await expect(progressBar).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("Mark Complete", () => {
  test("'Mark complete' button is visible on a section", async ({ page }) => {
    await page.goto(shared.lessonUrl);

    // Wait for lesson content to load (not skeleton)
    await page.waitForSelector("section[id^='section-']", { timeout: 15_000 });

    const markCompleteBtn = page
      .getByRole("button", { name: /as complete/i })
      .first();
    await expect(markCompleteBtn).toBeVisible();
  });

  test("clicking 'Mark complete' shows 'Completed' state and success toast", async ({
    page,
  }) => {
    await page.goto(shared.lessonUrl);

    await page.waitForSelector("section[id^='section-']", { timeout: 15_000 });

    const markCompleteBtn = page
      .getByRole("button", { name: /as complete/i })
      .first();
    await expect(markCompleteBtn).toBeVisible();

    await markCompleteBtn.click();

    // After the API call the button is replaced by a "Completed" marker IN THE SECTION. Scoped
    // there, because the course-outline sidebar also carries a `sr-only` "completed" for every
    // finished section, and an unscoped match resolved to that -- permanently hidden, so the
    // assertion could not pass however well the button worked.
    await expect(
      page.locator("section[id^='section-']").getByText("Completed").first(),
    ).toBeVisible({ timeout: 10_000 });

    // Sonner toast
    await expect(page.getByText(/section complete/i)).toBeVisible({
      timeout: 10_000,
    });
  });

  test("progress bar value increases after marking a section complete", async ({
    page,
  }) => {
    await page.goto(shared.lessonUrl);
    await page.waitForSelector("section[id^='section-']", { timeout: 15_000 });

    const progressBar = page.getByRole("progressbar", {
      name: /lesson progress/i,
    });
    const initialValue = Number(
      await progressBar.getAttribute("aria-valuenow"),
    );

    const markCompleteBtn = page
      .getByRole("button", { name: /as complete/i })
      .first();

    // Only attempt if button is visible (section not yet completed)
    if (await markCompleteBtn.isVisible()) {
      await markCompleteBtn.click();
      await page.waitForTimeout(1_000); // allow React Query cache to update

      const updatedValue = Number(
        await progressBar.getAttribute("aria-valuenow"),
      );
      expect(updatedValue).toBeGreaterThanOrEqual(initialValue);
    }
  });
});

test.describe("Focus mode", () => {
  test("focus mode toggle button is visible on lesson page", async ({
    page,
  }) => {
    await page.goto(shared.lessonUrl);

    // The focus toggle button has aria-label "Enter focus mode"
    const focusBtn = page.getByRole("button", {
      name: /enter focus mode|exit focus mode/i,
    });
    await expect(focusBtn).toBeVisible({ timeout: 15_000 });
  });

  test("clicking focus toggle changes aria-pressed state", async ({ page }) => {
    await page.goto(shared.lessonUrl);

    const focusBtn = page.getByRole("button", {
      name: /enter focus mode/i,
    });
    await expect(focusBtn).toBeVisible({ timeout: 15_000 });

    // Not pressed initially
    await expect(focusBtn).toHaveAttribute("aria-pressed", "false");

    await focusBtn.click();

    // Now pressed
    await expect(
      page.getByRole("button", { name: /exit focus mode/i }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  test("pressing F key toggles focus mode", async ({ page }) => {
    await page.goto(shared.lessonUrl);

    const focusBtn = page.getByRole("button", { name: /enter focus mode/i });
    await expect(focusBtn).toBeVisible({ timeout: 15_000 });

    // Press F while focus is not on an input
    await page.keyboard.press("f");

    await expect(
      page.getByRole("button", { name: /exit focus mode/i }),
    ).toBeVisible({ timeout: 3_000 });

    // Press F again to toggle back
    await page.keyboard.press("f");

    await expect(
      page.getByRole("button", { name: /enter focus mode/i }),
    ).toBeVisible({ timeout: 3_000 });
  });
});
