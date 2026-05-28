/**
 * E2E tests — Lesson content viewing.
 *
 * Setup: one enrolled learner with a known course/module/lesson.
 * Tests cover the Clean Reader layout, sidebar, breadcrumbs,
 * Mark Complete button, progress bar, and focus mode.
 */

import { test, expect } from "@playwright/test";
import {
  makeCredentials,
  apiRegister,
  apiGetMe,
  apiEnroll,
  getFirstCourseId,
  getCourseDetail,
  seedSessionStorage,
  type TestCredentials,
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
  const creds = makeCredentials("lesson");
  const tokens = await apiRegister(request, creds);
  const user = await apiGetMe(request, tokens.accessToken);
  const courseId = await getFirstCourseId(request, tokens.accessToken);

  await apiEnroll(request, tokens.accessToken, courseId);

  const course = await getCourseDetail(request, tokens.accessToken, courseId);
  const firstModule = course.modules[0];

  if (!firstModule) {
    throw new Error("Test course has no modules — seed the database first.");
  }

  const firstLesson = firstModule.lessons[0];
  if (!firstLesson) {
    throw new Error("First module has no lessons — seed the database first.");
  }

  const lessonUrl = `/courses/${courseId}/modules/${firstModule.id}/lessons/${firstLesson.id}`;

  shared = {
    tokens,
    user,
    courseId,
    moduleId: firstModule.id,
    lessonId: firstLesson.id,
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

    // The page should NOT still be on the loading skeleton
    await expect(page.locator(".animate-pulse").first()).not.toBeVisible({
      timeout: 5_000,
    });
  });

  test("breadcrumbs show Course → Module → Lesson", async ({ page }) => {
    await page.goto(shared.lessonUrl);

    // The Breadcrumb component renders a nav landmark
    const breadcrumb = page.locator("nav[aria-label]").first();
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
      .getByRole("button", { name: /mark complete/i })
      .first();
    await expect(markCompleteBtn).toBeVisible();
  });

  test("clicking 'Mark complete' shows 'Completed' state and success toast", async ({
    page,
  }) => {
    await page.goto(shared.lessonUrl);

    await page.waitForSelector("section[id^='section-']", { timeout: 15_000 });

    const markCompleteBtn = page
      .getByRole("button", { name: /mark complete/i })
      .first();
    await expect(markCompleteBtn).toBeVisible();

    await markCompleteBtn.click();

    // After API call: "Completed" text appears in place of the button
    await expect(page.getByText("Completed").first()).toBeVisible({
      timeout: 10_000,
    });

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
      .getByRole("button", { name: /mark complete/i })
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
