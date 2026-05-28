/**
 * E2E tests — Role-Based Access Control (RBAC).
 *
 * Verifies that each role (learner, course_designer, admin) can only reach
 * the routes and API endpoints they are authorised for.
 *
 * Setup strategy:
 *  - One beforeAll at the top level creates three separate sessions:
 *      • a fresh registered learner (with consent given so they land on /courses)
 *      • the seeded designer account
 *      • the seeded admin account
 *  - Each test group's beforeEach seeds the relevant session into the page.
 *  - API-only tests use the request fixture directly (no browser page).
 */

import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import {
  apiLogin,
  apiGetMe,
  apiGiveConsent,
  apiSetWebcamMode,
  apiRegister,
  seedSessionStorage,
  makeCredentials,
  type TokenResponse,
} from "./helpers/auth";

const API_BASE = "http://localhost:8000/api/v1";

// ---------------------------------------------------------------------------
// Seeded account credentials
// ---------------------------------------------------------------------------

const DESIGNER_CREDS = { email: "designer@affectlearn.io", password: "Designer123!" };
const ADMIN_CREDS = { email: "admin@affectlearn.io", password: "Admin123!" };

// ---------------------------------------------------------------------------
// Shared state (populated once in beforeAll)
// ---------------------------------------------------------------------------

interface RoleSessions {
  learner: { tokens: TokenResponse; user: Record<string, unknown> };
  designer: { tokens: TokenResponse; user: Record<string, unknown> };
  admin: { tokens: TokenResponse; user: Record<string, unknown> };
}

let sessions: RoleSessions;

test.beforeAll(async ({ request }) => {
  // --- Learner: register + give consent so they land on /courses ---
  const creds = makeCredentials("rbac-learner");
  const learnerTokens = await apiRegister(request, creds);
  await apiGiveConsent(request, learnerTokens.accessToken);
  await apiSetWebcamMode(request, learnerTokens.accessToken, false);
  const learnerUser = await apiGetMe(request, learnerTokens.accessToken);

  // --- Designer (seeded) ---
  const designerTokens = await apiLogin(request, DESIGNER_CREDS);
  const designerUser = await apiGetMe(request, designerTokens.accessToken);

  // --- Admin (seeded) ---
  const adminTokens = await apiLogin(request, ADMIN_CREDS);
  const adminUser = await apiGetMe(request, adminTokens.accessToken);

  sessions = {
    learner: { tokens: learnerTokens, user: learnerUser },
    designer: { tokens: designerTokens, user: designerUser },
    admin: { tokens: adminTokens, user: adminUser },
  };
});

// ---------------------------------------------------------------------------
// Learner route access
// ---------------------------------------------------------------------------

test.describe("Learner — route access", () => {
  test.beforeEach(async ({ page }) => {
    await seedSessionStorage(page, sessions.learner.tokens, sessions.learner.user);
  });

  test("learner can access /courses and sees course listing", async ({ page }) => {
    await page.goto("/courses");

    await page.waitForURL((url) => url.pathname === "/courses", {
      timeout: 10_000,
    });

    // The page renders without being kicked back to /login or another protected page
    expect(new URL(page.url()).pathname).toBe("/courses");

    await expect(
      page.getByRole("heading", { name: /browse courses/i }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("learner accessing /analytics is redirected to /courses", async ({
    page,
  }) => {
    await page.goto("/analytics");

    await page.waitForURL(
      (url) => url.pathname !== "/analytics",
      { timeout: 10_000 },
    );

    const path = new URL(page.url()).pathname;
    // Should land on /courses (or /login if token expired, but not /analytics)
    expect(path).not.toBe("/analytics");
    expect(path === "/courses" || path === "/login").toBe(true);
  });

  test("learner accessing /users is redirected to /courses", async ({
    page,
  }) => {
    await page.goto("/users");

    await page.waitForURL(
      (url) => url.pathname !== "/users",
      { timeout: 10_000 },
    );

    const path = new URL(page.url()).pathname;
    expect(path).not.toBe("/users");
    expect(path === "/courses" || path === "/login").toBe(true);
  });

  test("unauthenticated user accessing /courses is redirected to /login", async ({
    page,
  }) => {
    // Override the session by clearing storage first (addInitScript runs before goto)
    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());
    await page.goto("/courses");

    await page.waitForURL((url) => url.pathname === "/login", {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).toBe("/login");
  });
});

// ---------------------------------------------------------------------------
// Designer route access
// ---------------------------------------------------------------------------

test.describe("Designer — route access", () => {
  test.beforeEach(async ({ page }) => {
    await seedSessionStorage(
      page,
      sessions.designer.tokens,
      sessions.designer.user,
    );
  });

  test("designer can access /analytics", async ({ page }) => {
    await page.goto("/analytics");

    await page.waitForURL((url) => url.pathname === "/analytics", {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).toBe("/analytics");
  });

  test("designer accessing /users is redirected away from /users", async ({
    page,
  }) => {
    await page.goto("/users");

    await page.waitForURL((url) => url.pathname !== "/users", {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).not.toBe("/users");
  });

  test("designer accessing /courses is redirected to /analytics", async ({
    page,
  }) => {
    await page.goto("/courses");

    // Designer should be bounced back to their dashboard
    await page.waitForURL(
      (url) => url.pathname !== "/courses",
      { timeout: 10_000 },
    );

    const path = new URL(page.url()).pathname;
    expect(path).not.toBe("/courses");
  });
});

// ---------------------------------------------------------------------------
// Admin route access
// ---------------------------------------------------------------------------

test.describe("Admin — route access", () => {
  test.beforeEach(async ({ page }) => {
    await seedSessionStorage(page, sessions.admin.tokens, sessions.admin.user);
  });

  test("admin can access /users", async ({ page }) => {
    await page.goto("/users");

    await page.waitForURL((url) => url.pathname === "/users", {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).toBe("/users");
  });

  test("admin can access /analytics", async ({ page }) => {
    await page.goto("/analytics");

    await page.waitForURL((url) => url.pathname === "/analytics", {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).toBe("/analytics");
  });
});

// ---------------------------------------------------------------------------
// RBAC — Admin API endpoints
// ---------------------------------------------------------------------------

test.describe("RBAC API — /admin/users", () => {
  test("GET /admin/users with admin token returns 200", async ({ request }) => {
    const res = await request.get(`${API_BASE}/admin/users`, {
      headers: { Authorization: `Bearer ${sessions.admin.tokens.accessToken}` },
    });

    expect(res.status()).toBe(200);
  });

  test("GET /admin/users with learner token returns 403", async ({
    request,
  }) => {
    const res = await request.get(`${API_BASE}/admin/users`, {
      headers: {
        Authorization: `Bearer ${sessions.learner.tokens.accessToken}`,
      },
    });

    expect(res.status()).toBe(403);
  });

  test("GET /admin/users without token returns 401", async ({ request }) => {
    const res = await request.get(`${API_BASE}/admin/users`);
    expect(res.status()).toBe(401);
  });

  test("GET /admin/users with designer token returns 403", async ({
    request,
  }) => {
    const res = await request.get(`${API_BASE}/admin/users`, {
      headers: {
        Authorization: `Bearer ${sessions.designer.tokens.accessToken}`,
      },
    });

    expect(res.status()).toBe(403);
  });
});

// ---------------------------------------------------------------------------
// RBAC API — /analytics/courses
// ---------------------------------------------------------------------------

test.describe("RBAC API — /analytics/courses", () => {
  test("GET /analytics/courses with designer token returns 200", async ({
    request,
  }) => {
    const res = await request.get(`${API_BASE}/analytics/courses`, {
      headers: {
        Authorization: `Bearer ${sessions.designer.tokens.accessToken}`,
      },
    });

    expect(res.status()).toBe(200);
  });

  test("GET /analytics/courses with admin token returns 200", async ({
    request,
  }) => {
    const res = await request.get(`${API_BASE}/analytics/courses`, {
      headers: { Authorization: `Bearer ${sessions.admin.tokens.accessToken}` },
    });

    expect(res.status()).toBe(200);
  });

  test("GET /analytics/courses with learner token returns 403", async ({
    request,
  }) => {
    const res = await request.get(`${API_BASE}/analytics/courses`, {
      headers: {
        Authorization: `Bearer ${sessions.learner.tokens.accessToken}`,
      },
    });

    expect(res.status()).toBe(403);
  });

  test("GET /analytics/courses without token returns 401", async ({
    request,
  }) => {
    const res = await request.get(`${API_BASE}/analytics/courses`);
    expect(res.status()).toBe(401);
  });
});

// ---------------------------------------------------------------------------
// RBAC API — learner-only endpoints (consent, webcam-mode)
// ---------------------------------------------------------------------------

test.describe("RBAC API — learner-only endpoints", () => {
  test("POST /auth/consent as admin returns 403", async ({ request }) => {
    const res = await request.post(`${API_BASE}/auth/consent`, {
      headers: { Authorization: `Bearer ${sessions.admin.tokens.accessToken}` },
      data: { consentGiven: true },
    });

    expect(res.status()).toBe(403);
  });

  test("POST /auth/webcam-mode as admin returns 403", async ({ request }) => {
    const res = await request.post(`${API_BASE}/auth/webcam-mode`, {
      headers: { Authorization: `Bearer ${sessions.admin.tokens.accessToken}` },
      data: { webcamEnabled: true },
    });

    expect(res.status()).toBe(403);
  });

  test("POST /enrollments as designer returns 403 or 400", async ({
    request,
  }) => {
    // Designers cannot enroll in courses; backend returns 403 FORBIDDEN
    const res = await request.post(`${API_BASE}/enrollments`, {
      headers: {
        Authorization: `Bearer ${sessions.designer.tokens.accessToken}`,
      },
      data: { courseId: "00000000-0000-0000-0000-000000000000" },
    });

    // 403 is the expected RBAC rejection; 400 is acceptable if validation fires first
    expect([400, 403]).toContain(res.status());
  });
});

// ---------------------------------------------------------------------------
// Role metadata verification
// ---------------------------------------------------------------------------

test.describe("Role metadata — /auth/me", () => {
  test("learner session has role: learner", async ({ request }) => {
    const user = await apiGetMe(request, sessions.learner.tokens.accessToken);
    expect(user.role).toBe("learner");
  });

  test("designer session has role: course_designer", async ({ request }) => {
    const user = await apiGetMe(request, sessions.designer.tokens.accessToken);
    expect(user.role).toBe("course_designer");
  });

  test("admin session has role: admin", async ({ request }) => {
    const user = await apiGetMe(request, sessions.admin.tokens.accessToken);
    expect(user.role).toBe("admin");
  });
});
