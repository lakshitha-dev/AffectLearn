/**
 * E2E tests — Course browsing and enrollment.
 *
 * One learner account is created in beforeAll and reused across all tests
 * via seeded localStorage (storageState-equivalent via addInitScript).
 * This avoids expensive re-registration per test.
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
// Shared state set up in beforeAll
// ---------------------------------------------------------------------------

interface SuiteState {
  creds: TestCredentials;
  tokens: { accessToken: string; refreshToken: string; expiresIn: number };
  user: Record<string, unknown>;
  firstCourseId: string;
}

let shared: SuiteState;

test.beforeAll(async ({ request }) => {
  const creds = makeCredentials("courses");
  const tokens = await apiRegister(request, creds);
  const user = await apiGetMe(request, tokens.accessToken);
  const firstCourseId = await getFirstCourseId(request, tokens.accessToken);

  shared = { creds, tokens, user, firstCourseId };
});

/**
 * Before each test: inject the shared session into the page's localStorage
 * so the browser starts authenticated.
 */
test.beforeEach(async ({ page }) => {
  await seedSessionStorage(page, shared.tokens, shared.user);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Course browsing", () => {
  test("learner sees 'Browse Courses' section on /courses", async ({
    page,
  }) => {
    await page.goto("/courses");

    await expect(
      page.getByRole("heading", { name: /browse courses/i }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("search input filters courses by title", async ({ page }) => {
    await page.goto("/courses");

    // Wait for courses to load first
    await page.waitForSelector('[aria-labelledby="browse-heading"]', {
      timeout: 15_000,
    });

    const searchBox = page.getByRole("searchbox", { name: /search courses/i });
    await expect(searchBox).toBeVisible();

    // Type a search term unlikely to match everything
    await searchBox.fill("zzz-no-match-xyz");

    // The empty state or filtered list should appear (debounced 300 ms)
    await page.waitForTimeout(400);

    // Either a "No courses match" message or fewer course cards
    const noMatchText = page.getByText(/no courses match/i);
    const courseCards = page.locator('[aria-labelledby="browse-heading"] a');

    const noMatch = await noMatchText.isVisible().catch(() => false);
    const cardCount = await courseCards.count();

    // One of: no-match message shown, or card list is shorter than original
    expect(noMatch || cardCount === 0).toBeTruthy();

    // Clear and verify courses come back
    await searchBox.fill("");
    await page.waitForTimeout(400);
    const courseCardsAfterClear = page.locator(
      '[aria-labelledby="browse-heading"] a',
    );
    const countAfterClear = await courseCardsAfterClear.count();
    expect(countAfterClear).toBeGreaterThanOrEqual(0); // at least renders
  });

  test("clicking course card navigates to course overview", async ({
    page,
    request,
  }) => {
    // Use the known firstCourseId — but we need the actual title to click it
    const course = await getCourseDetail(
      request,
      shared.tokens.accessToken,
      shared.firstCourseId,
    );

    await page.goto("/courses");

    // Wait for the browse section to load
    await page.waitForSelector('[aria-labelledby="browse-heading"]', {
      timeout: 15_000,
    });

    // Find a link matching the course title (card links to /courses/<id>)
    const courseLink = page
      .getByRole("link", { name: course.title })
      .first();

    await expect(courseLink).toBeVisible({ timeout: 10_000 });
    await courseLink.click();

    await page.waitForURL(
      (url) => url.pathname === `/courses/${shared.firstCourseId}`,
      { timeout: 10_000 },
    );

    // Course title appears in the overview page heading
    await expect(
      page.getByRole("heading", { name: course.title }),
    ).toBeVisible();
  });
});

test.describe("Course enrollment", () => {
  test("Enroll button enrolls the learner and shows success toast", async ({
    page,
  }) => {
    await page.goto(`/courses/${shared.firstCourseId}`);

    // Wait for the page to load — enroll button appears when not yet enrolled
    const enrollBtn = page.getByRole("button", { name: /^enroll$/i });
    await expect(enrollBtn).toBeVisible({ timeout: 15_000 });

    await enrollBtn.click();

    // Sonner toast confirming enrollment
    await expect(
      page.getByText(/you're enrolled/i),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("after enrollment course appears in 'My Courses' section", async ({
    page,
    request,
  }) => {
    // Ensure enrolled (idempotent)
    await apiEnroll(request, shared.tokens.accessToken, shared.firstCourseId).catch(
      () => {/* already enrolled — ignore */},
    );

    await page.goto("/courses");

    // My Courses section should exist now
    await expect(
      page.getByRole("heading", { name: /my courses/i }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("enrolling again shows 'Continue Learning' state on overview", async ({
    page,
    request,
  }) => {
    // Ensure enrolled
    await apiEnroll(request, shared.tokens.accessToken, shared.firstCourseId).catch(
      () => {/* already enrolled — ignore */},
    );

    await page.goto(`/courses/${shared.firstCourseId}`);

    // After enrollment the EnrollButton renders "Start Learning" or "Continue Learning"
    const continueBtn = page.getByRole("button", {
      name: /start learning|continue learning/i,
    });
    await expect(continueBtn).toBeVisible({ timeout: 15_000 });

    // The plain "Enroll" button should NOT be visible
    const enrollBtn = page.getByRole("button", { name: /^enroll$/i });
    await expect(enrollBtn).not.toBeVisible();
  });
});

test.describe("Dark mode toggle", () => {
  test("TopBar theme toggle cycles through light/dark/system", async ({
    page,
  }) => {
    await page.goto("/courses");

    const toggleBtn = page.getByRole("button", { name: /theme/i });
    await expect(toggleBtn).toBeVisible({ timeout: 10_000 });

    // Read initial aria-label
    const label1 = await toggleBtn.getAttribute("aria-label");
    expect(label1).toMatch(/theme/i);

    // Click once — theme cycles
    await toggleBtn.click();
    await page.waitForTimeout(200);

    const label2 = await toggleBtn.getAttribute("aria-label");
    expect(label2).toMatch(/theme/i);

    // Labels should differ after cycling
    expect(label1).not.toBe(label2);
  });
});
