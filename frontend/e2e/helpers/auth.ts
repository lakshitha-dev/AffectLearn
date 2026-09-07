import type { APIRequestContext, Page } from "@playwright/test";

const API_BASE = "http://localhost:8000/api/v1";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TestCredentials {
  email: string;
  password: string;
  firstName: string;
  lastName: string;
}

export interface TokenResponse {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}

// ---------------------------------------------------------------------------
// Credential factory
// ---------------------------------------------------------------------------

/**
 * Generate unique credentials for an isolated test user.
 * The timestamp suffix guarantees no collision across parallel runs.
 */
export function makeCredentials(prefix = "learner"): TestCredentials {
  const ts = Date.now();
  return {
    email: `test-${prefix}-${ts}@test.com`,
    password: "Password1!",
    firstName: "Test",
    lastName: "User",
  };
}

// ---------------------------------------------------------------------------
// API helpers — auth
// ---------------------------------------------------------------------------

/**
 * Register a new learner account via the backend REST API.
 * Returns the raw token response so callers can seed localStorage if needed.
 */
export async function apiRegister(
  request: APIRequestContext,
  creds: TestCredentials,
): Promise<TokenResponse> {
  const res = await request.post(`${API_BASE}/auth/register`, {
    data: {
      emailAddress: creds.email,
      password: creds.password,
      firstName: creds.firstName,
      lastName: creds.lastName,
      ageRange: "18-24",
      degreeProgram: "Computer Science",
    },
  });

  if (!res.ok()) {
    const body = await res.text();
    throw new Error(`Registration failed (${res.status()}): ${body}`);
  }

  return res.json();
}

/**
 * Log in via the backend REST API and return tokens.
 */
export async function apiLogin(
  request: APIRequestContext,
  creds: Pick<TestCredentials, "email" | "password">,
): Promise<TokenResponse> {
  const res = await request.post(`${API_BASE}/auth/login`, {
    data: {
      emailAddress: creds.email,
      password: creds.password,
    },
  });

  if (!res.ok()) {
    const body = await res.text();
    throw new Error(`Login failed (${res.status()}): ${body}`);
  }

  return res.json();
}

/**
 * Fetch /auth/me using a bearer token and return the user object.
 */
export async function apiGetMe(
  request: APIRequestContext,
  accessToken: string,
): Promise<Record<string, unknown>> {
  const res = await request.get(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!res.ok()) {
    throw new Error(`GET /auth/me failed (${res.status()})`);
  }

  return res.json();
}

/**
 * Give consent to the research study via the API.
 * Only valid for learner accounts; designers/admins receive 403.
 */
export async function apiGiveConsent(
  request: APIRequestContext,
  accessToken: string,
): Promise<void> {
  const res = await request.post(`${API_BASE}/auth/consent`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: { consentGiven: true },
  });

  if (!res.ok()) {
    const body = await res.text();
    throw new Error(`POST /auth/consent failed (${res.status()}): ${body}`);
  }
}

/**
 * Set webcam mode for the authenticated learner via the API.
 * Only valid for learner accounts; designers/admins receive 403.
 */
export async function apiSetWebcamMode(
  request: APIRequestContext,
  accessToken: string,
  webcamEnabled: boolean,
): Promise<void> {
  const res = await request.post(`${API_BASE}/auth/webcam-mode`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: { webcamEnabled },
  });

  if (!res.ok()) {
    const body = await res.text();
    throw new Error(`POST /auth/webcam-mode failed (${res.status()}): ${body}`);
  }
}

// ---------------------------------------------------------------------------
// Session seeding
// ---------------------------------------------------------------------------

/**
 * Seed the Zustand session store in localStorage so the browser treats the
 * test user as already authenticated — no need to fill the login form.
 *
 * Call this BEFORE page.goto() so the store is available on first render.
 */
export async function seedSessionStorage(
  page: Page,
  tokens: TokenResponse,
  user: Record<string, unknown>,
): Promise<void> {
  const state = {
    state: {
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
      expiresAt: Date.now() + tokens.expiresIn * 1000,
      user,
    },
    version: 0,
  };

  await page.addInitScript((serialised) => {
    localStorage.setItem("affectlearn-session", serialised);
  }, JSON.stringify(state));
}

/**
 * Register a fresh user via the API, then inject their session into the page
 * so every test starts authenticated without going through the login UI.
 */
export async function registerAndSeedSession(
  request: APIRequestContext,
  page: Page,
  prefix = "learner",
): Promise<{
  creds: TestCredentials;
  tokens: TokenResponse;
  user: Record<string, unknown>;
}> {
  const creds = makeCredentials(prefix);
  const tokens = await apiRegister(request, creds);
  const user = await apiGetMe(request, tokens.accessToken);
  await seedSessionStorage(page, tokens, user);
  return { creds, tokens, user };
}

/**
 * Clear the Zustand session from localStorage, simulating a logout.
 * The next navigation will be treated as unauthenticated.
 */
export async function clearSession(page: Page): Promise<void> {
  await page.evaluate(() => {
    localStorage.removeItem("affectlearn-session");
  });
}

// ---------------------------------------------------------------------------
// Seeded account logins
// ---------------------------------------------------------------------------

/** Credentials for the seeded designer account. */
export const DESIGNER_CREDS = {
  email: "designer@affectlearn.io",
  password: "Designer123!",
};

/** Credentials for the seeded admin account. */
const ADMIN_CREDS = {
  email: "admin@affectlearn.io",
  password: "Admin123!",
};

/**
 * Log in as the seeded course designer and inject the session into the page.
 * Returns tokens and user for downstream assertions.
 */
export async function loginAsDesigner(
  request: APIRequestContext,
  page: Page,
): Promise<{ tokens: TokenResponse; user: Record<string, unknown> }> {
  const tokens = await apiLogin(request, DESIGNER_CREDS);
  const user = await apiGetMe(request, tokens.accessToken);
  await seedSessionStorage(page, tokens, user);
  return { tokens, user };
}

/**
 * Log in as the seeded admin and inject the session into the page.
 * Returns tokens and user for downstream assertions.
 */
export async function loginAsAdmin(
  request: APIRequestContext,
  page: Page,
): Promise<{ tokens: TokenResponse; user: Record<string, unknown> }> {
  const tokens = await apiLogin(request, ADMIN_CREDS);
  const user = await apiGetMe(request, tokens.accessToken);
  await seedSessionStorage(page, tokens, user);
  return { tokens, user };
}

/**
 * Create a fully-onboarded learner: registers, gives consent, sets webcam mode.
 * The user object in localStorage is updated with consentGivenAt so the app
 * skips /onboarding and goes directly to /courses.
 */
export async function createOnboardedLearner(
  request: APIRequestContext,
  page: Page,
  prefix = "onboarded",
): Promise<{
  creds: TestCredentials;
  tokens: TokenResponse;
  user: Record<string, unknown>;
}> {
  const creds = makeCredentials(prefix);
  const tokens = await apiRegister(request, creds);

  await apiGiveConsent(request, tokens.accessToken);
  await apiSetWebcamMode(request, tokens.accessToken, false);

  // Re-fetch so consentGivenAt is present in the user object
  const user = await apiGetMe(request, tokens.accessToken);
  await seedSessionStorage(page, tokens, user);
  return { creds, tokens, user };
}

// ---------------------------------------------------------------------------
// UI helpers
// ---------------------------------------------------------------------------

/**
 * Full UI registration: fills both form steps and waits for redirect.
 * Useful for the auth spec which intentionally tests the UI flow.
 */
export async function registerViaUi(
  page: Page,
  creds: TestCredentials,
): Promise<void> {
  await page.goto("/register");

  // Step 1 — credentials
  await page.getByLabel(/email/i).fill(creds.email);
  await page.locator("#password").fill(creds.password);
  await page.getByRole("button", { name: /continue/i }).click();

  // Step 2 — profile
  await page.getByLabel(/first name/i).fill(creds.firstName);
  await page.getByLabel(/last name/i).fill(creds.lastName);
  await page.getByRole("button", { name: /create account/i }).click();
}

/**
 * Full UI login: fills the sign-in form and waits for navigation away from /login.
 */
export async function loginViaUi(
  page: Page,
  creds: Pick<TestCredentials, "email" | "password">,
): Promise<void> {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(creds.email);
  await page.getByLabel(/password/i).fill(creds.password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), {
    timeout: 15_000,
  });
}

// ---------------------------------------------------------------------------
// Course helpers
// ---------------------------------------------------------------------------

/**
 * Enroll a learner in a course via the API.
 */
export async function apiEnroll(
  request: APIRequestContext,
  accessToken: string,
  courseId: string,
): Promise<void> {
  const res = await request.post(`${API_BASE}/enrollments`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: { courseId },
  });

  if (!res.ok()) {
    const body = await res.text();
    throw new Error(`Enrollment failed (${res.status()}): ${body}`);
  }
}

/**
 * Fetch the published course list and return the first course id.
 * Throws if no courses are available.
 */
export async function getFirstCourseId(
  request: APIRequestContext,
  accessToken: string,
): Promise<string> {
  const res = await request.get(`${API_BASE}/courses?page=1&pageSize=1`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!res.ok()) {
    throw new Error(`GET /courses failed (${res.status()})`);
  }

  const body = await res.json();
  const items: Array<{ id: string }> = body.items ?? [];
  if (items.length === 0) {
    throw new Error("No published courses found in the database.");
  }

  return items[0].id;
}

/**
 * Fetch full course detail (including modules/lessons) for a given courseId.
 */
export async function getCourseDetail(
  request: APIRequestContext,
  accessToken: string,
  courseId: string,
): Promise<{
  id: string;
  title: string;
  modules: Array<{
    id: string;
    title: string;
    lessons: Array<{ id: string; title: string }>;
  }>;
}> {
  const res = await request.get(`${API_BASE}/courses/${courseId}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!res.ok()) {
    throw new Error(`GET /courses/${courseId} failed (${res.status()})`);
  }

  return res.json();
}
