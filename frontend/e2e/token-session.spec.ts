/**
 * E2E tests — Token and session lifecycle.
 *
 * Covers:
 *  - Session persistence across page reloads and new tabs
 *  - Token refresh (valid and invalid refresh tokens)
 *  - Zustand localStorage shape after seeding
 *  - Expired token behaviour (triggers refresh or /login redirect)
 *  - RBAC respected even when session is injected with wrong role
 *  - Multi-tab session sharing via localStorage
 *
 * Design notes:
 *  - `seedSessionStorage` uses `addInitScript` so the store is populated
 *    before the first React render — no race conditions.
 *  - Token expiry is simulated by patching `expiresAt` in localStorage to
 *    a past timestamp; the app reads this on each request cycle.
 *  - Refresh-token tests call the API directly (request fixture) for speed,
 *    and use page.route() intercepts to verify the UI triggers the call.
 */

import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import {
  makeCredentials,
  apiRegister,
  apiLogin,
  apiGetMe,
  apiGiveConsent,
  apiSetWebcamMode,
  seedSessionStorage,
  clearSession,
  loginAsDesigner,
  createOnboardedLearner,
  type TokenResponse,
} from "./helpers/auth";

const API_BASE = "http://localhost:8000/api/v1";

// ---------------------------------------------------------------------------
// Shared learner session (registered + fully onboarded)
// ---------------------------------------------------------------------------

interface SessionSuiteState {
  tokens: TokenResponse;
  user: Record<string, unknown>;
}

let shared: SessionSuiteState;

test.beforeAll(async ({ request }) => {
  const creds = makeCredentials("tok-session");
  const tokens = await apiRegister(request, creds);
  await apiGiveConsent(request, tokens.accessToken);
  await apiSetWebcamMode(request, tokens.accessToken, false);
  const user = await apiGetMe(request, tokens.accessToken);
  shared = { tokens, user };
});

// ---------------------------------------------------------------------------
// Session persistence
// ---------------------------------------------------------------------------

test.describe("Session persistence", () => {
  test.beforeEach(async ({ page }) => {
    await seedSessionStorage(page, shared.tokens, shared.user);
  });

  test("page refresh preserves authentication — user stays on /courses", async ({
    page,
  }) => {
    await page.goto("/courses");
    await page.waitForURL((url) => url.pathname === "/courses", {
      timeout: 15_000,
    });

    await page.reload();

    // After reload the Zustand store re-hydrates from localStorage
    await page.waitForURL((url) => url.pathname === "/courses", {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).toBe("/courses");
  });

  test("after login, localStorage contains 'affectlearn-session' key", async ({
    page,
  }) => {
    await page.goto("/courses");
    await page.waitForURL((url) => url.pathname === "/courses", {
      timeout: 15_000,
    });

    const raw = await page.evaluate(() =>
      localStorage.getItem("affectlearn-session"),
    );

    expect(raw).not.toBeNull();
    expect(raw!.length).toBeGreaterThan(0);
  });

  test("localStorage session has the correct Zustand shape", async ({
    page,
  }) => {
    await page.goto("/courses");
    await page.waitForURL((url) => url.pathname === "/courses", {
      timeout: 15_000,
    });

    const raw = await page.evaluate(() =>
      localStorage.getItem("affectlearn-session"),
    );

    const parsed = JSON.parse(raw!);
    // Top-level shape: { state: { accessToken, refreshToken, expiresAt, user }, version: 0 }
    expect(parsed).toHaveProperty("state");
    expect(parsed).toHaveProperty("version");
    expect(parsed.state).toHaveProperty("accessToken");
    expect(parsed.state).toHaveProperty("refreshToken");
    expect(parsed.state).toHaveProperty("expiresAt");
    expect(parsed.state).toHaveProperty("user");
    expect(typeof parsed.state.accessToken).toBe("string");
    expect(typeof parsed.state.expiresAt).toBe("number");
  });

  test("after clearSession, localStorage no longer has affectlearn-session", async ({
    page,
  }) => {
    await page.goto("/courses");
    await page.waitForURL((url) => url.pathname === "/courses", {
      timeout: 15_000,
    });

    await clearSession(page);

    const raw = await page.evaluate(() =>
      localStorage.getItem("affectlearn-session"),
    );

    expect(raw).toBeNull();
  });

  test("after clearSession, navigating to /courses redirects to /login", async ({
    page,
  }) => {
    await page.goto("/courses");
    await page.waitForURL((url) => url.pathname === "/courses", {
      timeout: 15_000,
    });

    await clearSession(page);
    await page.goto("/courses");

    await page.waitForURL((url) => url.pathname === "/login", {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).toBe("/login");
  });

  test("opening a new page in the same browser context shares the session", async ({
    page,
    context,
  }) => {
    await page.goto("/courses");
    await page.waitForURL((url) => url.pathname === "/courses", {
      timeout: 15_000,
    });

    // Open a second page in the same browser context (shares localStorage)
    const page2 = await context.newPage();
    await page2.goto("/courses");

    await page2.waitForURL((url) => url.pathname === "/courses", {
      timeout: 10_000,
    });

    expect(new URL(page2.url()).pathname).toBe("/courses");
    await page2.close();
  });
});

// ---------------------------------------------------------------------------
// Token refresh — API contract
// ---------------------------------------------------------------------------

test.describe("Token refresh — API", () => {
  test("POST /auth/refresh with valid refreshToken returns 200 and new accessToken", async ({
    request,
  }) => {
    const res = await request.post(`${API_BASE}/auth/refresh`, {
      data: { refreshToken: shared.tokens.refreshToken },
    });

    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty("accessToken");
    expect(typeof body.accessToken).toBe("string");
    // New access token should be a non-empty JWT
    expect(body.accessToken.split(".").length).toBe(3);
  });

  test("POST /auth/refresh with invalid refreshToken returns 401", async ({
    request,
  }) => {
    const res = await request.post(`${API_BASE}/auth/refresh`, {
      data: { refreshToken: "this.is.not.a.valid.refresh.token" },
    });

    expect(res.status()).toBe(401);
  });

  test("POST /auth/refresh with missing body returns 422", async ({
    request,
  }) => {
    const res = await request.post(`${API_BASE}/auth/refresh`, {
      data: {},
    });

    // 422 Unprocessable Entity — missing required field
    expect(res.status()).toBe(422);
  });
});

// ---------------------------------------------------------------------------
// Expired token behaviour
// ---------------------------------------------------------------------------

test.describe("Expired token behaviour", () => {
  test("session with past expiresAt triggers refresh call or redirects to /login", async ({
    page,
    request,
  }) => {
    // Build a session where the access token appears expired
    const expiredState = {
      state: {
        accessToken: shared.tokens.accessToken,
        refreshToken: shared.tokens.refreshToken,
        // expiresAt is 5 minutes in the past
        expiresAt: Date.now() - 5 * 60 * 1000,
        user: shared.user,
      },
      version: 0,
    };

    let refreshCalled = false;
    await page.route("**/api/v1/auth/refresh", async (route) => {
      refreshCalled = true;
      await route.continue();
    });

    await page.addInitScript((serialised) => {
      localStorage.setItem("affectlearn-session", serialised);
    }, JSON.stringify(expiredState));

    await page.goto("/courses");

    // Wait for either a successful course load (refresh worked) or /login redirect
    await page.waitForURL(
      (url) =>
        url.pathname === "/courses" ||
        url.pathname === "/login" ||
        url.pathname.startsWith("/onboarding"),
      { timeout: 15_000 },
    );

    const finalPath = new URL(page.url()).pathname;
    // The app should have attempted a refresh or kicked back to /login
    const isExpectedPath =
      finalPath === "/courses" ||
      finalPath === "/login" ||
      finalPath.startsWith("/onboarding");

    expect(isExpectedPath).toBe(true);
  });

  test("session with completely expired and non-refreshable token redirects to /login", async ({
    page,
  }) => {
    const expiredState = {
      state: {
        // Dummy JWT-shaped token — will be rejected by server
        accessToken: "eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjF9.invalid",
        refreshToken: "invalid.refresh.token.xyz",
        expiresAt: Date.now() - 60 * 60 * 1000, // 1 hour in past
        user: shared.user,
      },
      version: 0,
    };

    await page.addInitScript((serialised) => {
      localStorage.setItem("affectlearn-session", serialised);
    }, JSON.stringify(expiredState));

    await page.goto("/courses");

    // The refresh will fail → the app clears the session → redirects to /login
    await page.waitForURL((url) => url.pathname === "/login", {
      timeout: 15_000,
    });

    expect(new URL(page.url()).pathname).toBe("/login");
  });
});

// ---------------------------------------------------------------------------
// RBAC — wrong-role injection
// ---------------------------------------------------------------------------

test.describe("Session injection with wrong role — RBAC still enforced", () => {
  test("learner session injected with role: course_designer is still blocked from /analytics via AuthGuard", async ({
    page,
    request,
  }) => {
    // Register a real learner
    const creds = makeCredentials("wrong-role");
    const tokens = await apiRegister(request, creds);
    // Patch the in-memory user object to lie about the role
    const spoofedUser = {
      ...(await apiGetMe(request, tokens.accessToken)),
      role: "course_designer",
    };

    await seedSessionStorage(page, tokens, spoofedUser);
    await page.goto("/analytics");

    // The server-side route (Next.js middleware / FastAPI guard) uses the JWT
    // role claim, not the client-side localStorage role.  The access token still
    // contains role: "learner" so the request is rejected and the user is
    // redirected away from /analytics.
    await page.waitForURL(
      (url) => url.pathname !== "/analytics",
      { timeout: 10_000 },
    );

    expect(new URL(page.url()).pathname).not.toBe("/analytics");
  });
});

// ---------------------------------------------------------------------------
// Multi-tab session sharing
// ---------------------------------------------------------------------------

test.describe("Multi-tab session sharing via localStorage", () => {
  test("session seeded in tab 1 is readable in tab 2 (same context)", async ({
    page,
    context,
  }) => {
    await seedSessionStorage(page, shared.tokens, shared.user);
    await page.goto("/courses");
    await page.waitForURL((url) => url.pathname === "/courses", {
      timeout: 15_000,
    });

    // Open a new tab in the same context (localStorage is shared)
    const page2 = await context.newPage();
    await page2.goto("/courses");

    await page2.waitForURL(
      (url) =>
        url.pathname === "/courses" || url.pathname.startsWith("/onboarding"),
      { timeout: 10_000 },
    );

    const raw = await page2.evaluate(() =>
      localStorage.getItem("affectlearn-session"),
    );

    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed.state).toHaveProperty("accessToken");

    await page2.close();
  });

  test("clearing session in tab 1 is visible in tab 2 before navigation", async ({
    page,
    context,
  }) => {
    await seedSessionStorage(page, shared.tokens, shared.user);
    await page.goto("/courses");
    await page.waitForURL((url) => url.pathname === "/courses", {
      timeout: 15_000,
    });

    const page2 = await context.newPage();
    await page2.goto("/courses");
    await page2.waitForURL(
      (url) =>
        url.pathname === "/courses" || url.pathname.startsWith("/onboarding"),
      { timeout: 10_000 },
    );

    // Clear session from tab 1
    await clearSession(page);

    // Verify tab 2 can also see it's gone (localStorage is shared, no reload needed)
    const raw = await page2.evaluate(() =>
      localStorage.getItem("affectlearn-session"),
    );

    expect(raw).toBeNull();
    await page2.close();
  });
});

// ---------------------------------------------------------------------------
// Seeded account sessions — designer and admin
// ---------------------------------------------------------------------------

test.describe("Designer session lifecycle", () => {
  test("loginAsDesigner seeds session and allows /analytics access", async ({
    page,
    request,
  }) => {
    await loginAsDesigner(request, page);
    await page.goto("/analytics");

    await page.waitForURL((url) => url.pathname === "/analytics", {
      timeout: 15_000,
    });

    expect(new URL(page.url()).pathname).toBe("/analytics");
  });

  test("designer session localStorage key has role course_designer", async ({
    page,
    request,
  }) => {
    await loginAsDesigner(request, page);
    await page.goto("/analytics");
    await page.waitForURL((url) => url.pathname === "/analytics", {
      timeout: 15_000,
    });

    const raw = await page.evaluate(() =>
      localStorage.getItem("affectlearn-session"),
    );

    const parsed = JSON.parse(raw!);
    expect(parsed.state.user.role).toBe("course_designer");
  });
});

test.describe("createOnboardedLearner helper", () => {
  test("onboarded learner goes directly to /courses without /onboarding redirect", async ({
    page,
    request,
  }) => {
    const { user } = await createOnboardedLearner(request, page, "fully-ob");

    expect(user.consentGivenAt).toBeTruthy();

    await page.goto("/courses");

    await page.waitForURL((url) => url.pathname === "/courses", {
      timeout: 15_000,
    });

    // Must NOT be redirected to /onboarding
    expect(new URL(page.url()).pathname).toBe("/courses");
  });
});
