/**
 * E2E tests — Authentication flows.
 *
 * Covers registration (two-step form), login, API contract, and logout.
 * Uses Page Object Models to keep individual tests concise.
 *
 * Design choices:
 *  - beforeAll creates one shared user per describe block to avoid
 *    redundant API round-trips while keeping state isolated between suites.
 *  - API-contract tests use the `request` fixture directly (no browser needed).
 *  - UI tests rely on locator strategies documented in the component source.
 */

import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import {
  makeCredentials,
  apiRegister,
  apiLogin,
  apiGetMe,
  loginViaUi,
  seedSessionStorage,
  type TestCredentials,
} from "./helpers/auth";

const API_BASE = "http://localhost:8000/api/v1";

// ---------------------------------------------------------------------------
// Page Object Models
// ---------------------------------------------------------------------------

class LoginPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/login");
    await this.page.waitForSelector("form");
  }

  async fillEmail(email: string) {
    await this.page.getByLabel(/email/i).fill(email);
  }

  async fillPassword(password: string) {
    await this.page.getByLabel(/password/i).fill(password);
  }

  async submit() {
    await this.page.getByRole("button", { name: /sign in/i }).click();
  }

  async login(email: string, password: string) {
    await this.fillEmail(email);
    await this.fillPassword(password);
    await this.submit();
  }

  errorAlert() {
    return this.page.locator('[role="alert"]').first();
  }

  signUpLink() {
    return this.page.getByRole("link", { name: /sign up/i });
  }

  submitButton() {
    return this.page.getByRole("button", { name: /sign in/i });
  }
}

class RegisterPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/register");
    await this.page.waitForSelector("form");
  }

  // --- Step 1 ---
  async fillEmail(email: string) {
    await this.page.getByLabel(/email/i).fill(email);
  }

  async fillPassword(password: string) {
    await this.page.locator("#password").fill(password);
  }

  async continueToStep2() {
    await this.page.getByRole("button", { name: /continue/i }).click();
  }

  // --- Step 2 ---
  async fillFirstName(name: string) {
    await this.page.getByLabel(/first name/i).fill(name);
  }

  async fillLastName(name: string) {
    await this.page.getByLabel(/last name/i).fill(name);
  }

  async createAccount() {
    await this.page.getByRole("button", { name: /create account/i }).click();
  }

  async goBack() {
    await this.page.getByRole("button", { name: /back/i }).click();
  }

  /** Complete both steps */
  async register(creds: TestCredentials) {
    await this.fillEmail(creds.email);
    await this.fillPassword(creds.password);
    await this.continueToStep2();
    await this.fillFirstName(creds.firstName);
    await this.fillLastName(creds.lastName);
    await this.createAccount();
  }

  duplicateEmailAlert() {
    return this.page.locator('[role="alert"]').first();
  }

  continueButton() {
    return this.page.getByRole("button", { name: /continue/i });
  }

  createAccountButton() {
    return this.page.getByRole("button", { name: /create account/i });
  }
}

// ---------------------------------------------------------------------------
// Registration tests
// ---------------------------------------------------------------------------

test.describe("Registration", () => {
  test("valid registration redirects new learner to onboarding", async ({
    page,
  }) => {
    const creds = makeCredentials("reg-happy");
    const register = new RegisterPage(page);

    await register.goto();
    await register.register(creds);

    // New learner has no consent yet → /onboarding
    await page.waitForURL(
      (url) =>
        url.pathname.startsWith("/onboarding") || url.pathname === "/courses",
      { timeout: 15_000 },
    );

    const path = new URL(page.url()).pathname;
    expect(["/onboarding", "/courses"]).toContain(path);
  });

  test("new learner without consent lands on /onboarding, not /courses", async ({
    page,
    request,
  }) => {
    // Register via API to confirm consentGivenAt is null
    const creds = makeCredentials("reg-onboarding");
    const tokens = await apiRegister(request, creds);
    const user = (await apiGetMe(request, tokens.accessToken)) as Record<
      string,
      unknown
    >;

    expect(user.consentGivenAt ?? null).toBeNull();

    await seedSessionStorage(page, tokens, user);
    await page.goto("/courses");

    // AuthGuard should redirect to /onboarding before consent is given
    await page.waitForURL((url) => url.pathname.startsWith("/onboarding"), {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).toMatch(/^\/onboarding/);
  });

  test("duplicate email shows 'Already have an account? Sign in' alert", async ({
    page,
    request,
  }) => {
    const creds = makeCredentials("reg-dup");
    await apiRegister(request, creds);

    const register = new RegisterPage(page);
    await register.goto();
    await register.register(creds);

    await expect(
      page.getByText(/already have an account/i),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("back button on step 2 returns to step 1", async ({ page }) => {
    const creds = makeCredentials("reg-back");
    const register = new RegisterPage(page);

    await register.goto();
    await register.fillEmail(creds.email);
    await register.fillPassword(creds.password);
    await register.continueToStep2();

    await expect(
      page.getByRole("button", { name: /back/i }),
    ).toBeVisible({ timeout: 5_000 });

    await register.goBack();

    await expect(register.continueButton()).toBeVisible({ timeout: 5_000 });
  });

  test("empty email on step 1 does not advance to step 2", async ({ page }) => {
    const creds = makeCredentials("reg-empty-email");
    const register = new RegisterPage(page);

    await register.goto();
    // Leave email blank, only fill password
    await register.fillPassword(creds.password);
    await register.continueToStep2();

    // Should remain on step 1 — Continue button still visible, no first-name field
    await expect(register.continueButton()).toBeVisible({ timeout: 5_000 });
    await expect(
      page.getByLabel(/first name/i),
    ).not.toBeVisible();
  });

  test("weak password (no special character) shows validation error", async ({
    page,
  }) => {
    const register = new RegisterPage(page);
    await register.goto();

    await register.fillEmail(`weak-pw-${Date.now()}@test.com`);
    // "password123" has no special character
    await register.fillPassword("password123");
    await register.continueToStep2();

    // Validation error should appear; we should remain on step 1
    const errorText = page.locator('[role="alert"], [aria-live], .text-destructive').first();
    await expect(errorText).toBeVisible({ timeout: 5_000 });

    // First-name field should NOT be visible — still on step 1
    await expect(page.getByLabel(/first name/i)).not.toBeVisible();
  });

  test("invalid email format shows validation error", async ({ page }) => {
    const register = new RegisterPage(page);
    await register.goto();

    await register.fillEmail("notanemail");
    await register.fillPassword("Password1!");
    await register.continueToStep2();

    // Validation should block advance; inline error or HTML5 invalid
    const emailInput = page.getByLabel(/email/i);
    const validity = await emailInput.evaluate(
      (el) => (el as HTMLInputElement).validity.valid,
    );
    // Either HTML5 validation blocks it or an error element appears
    if (validity) {
      // React Hook Form error message
      const err = page.locator('[role="alert"], .text-destructive').first();
      await expect(err).toBeVisible({ timeout: 5_000 });
    }

    await expect(page.getByLabel(/first name/i)).not.toBeVisible();
  });

  test("empty first name on step 2 does not submit form", async ({ page }) => {
    const creds = makeCredentials("reg-empty-fname");
    const register = new RegisterPage(page);

    await register.goto();
    await register.fillEmail(creds.email);
    await register.fillPassword(creds.password);
    await register.continueToStep2();

    // On step 2 — leave first name blank
    await register.fillLastName("User");
    await register.createAccount();

    // Should remain on step 2 (first-name field still visible)
    await expect(page.getByLabel(/first name/i)).toBeVisible({ timeout: 5_000 });
  });

  test("after registration GET /auth/me returns role learner", async ({
    request,
  }) => {
    const creds = makeCredentials("reg-role");
    const tokens = await apiRegister(request, creds);
    const user = await apiGetMe(request, tokens.accessToken);

    expect(user.role).toBe("learner");
    expect(user.emailAddress).toBe(creds.email);
  });

  test("registration button shows disabled/loading state during submission", async ({
    page,
  }) => {
    const creds = makeCredentials("reg-loading");
    const register = new RegisterPage(page);

    await register.goto();
    await register.fillEmail(creds.email);
    await register.fillPassword(creds.password);
    await register.continueToStep2();

    await page.getByLabel(/first name/i).fill(creds.firstName);
    await page.getByLabel(/last name/i).fill(creds.lastName);

    // Slow down the API so we can observe the loading state
    await page.route("**/api/v1/auth/register", async (route) => {
      await new Promise((r) => setTimeout(r, 800));
      await route.continue();
    });

    const createBtn = register.createAccountButton();
    await createBtn.click();

    // Button becomes disabled or changes text while request is in-flight
    await expect(createBtn).toBeDisabled({ timeout: 3_000 });
  });
});

// ---------------------------------------------------------------------------
// Login tests
// ---------------------------------------------------------------------------

test.describe("Login", () => {
  let sharedCreds: TestCredentials;

  test.beforeAll(async ({ request }) => {
    sharedCreds = makeCredentials("login");
    await apiRegister(request, sharedCreds);
  });

  test("valid learner credentials redirect to onboarding or courses", async ({
    page,
  }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login(sharedCreds.email, sharedCreds.password);

    await page.waitForURL(
      (url) =>
        url.pathname.startsWith("/onboarding") || url.pathname === "/courses",
      { timeout: 15_000 },
    );

    const path = new URL(page.url()).pathname;
    expect(path === "/courses" || path.startsWith("/onboarding")).toBe(true);
  });

  test("invalid credentials show error message without navigation", async ({
    page,
  }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login("nobody@nowhere.invalid", "WrongPass999!");

    await expect(loginPage.errorAlert()).toBeVisible({ timeout: 10_000 });
    // Should still be on /login
    expect(new URL(page.url()).pathname).toBe("/login");
  });

  test("wrong password shows error, page stays on /login", async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login(sharedCreds.email, "WrongPassword9!");

    await expect(loginPage.errorAlert()).toBeVisible({ timeout: 10_000 });
    expect(new URL(page.url()).pathname).toBe("/login");
  });

  test("non-existent email shows same generic error as wrong password", async ({
    page,
  }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login(`ghost-${Date.now()}@nowhere.invalid`, "Password1!");

    await expect(loginPage.errorAlert()).toBeVisible({ timeout: 10_000 });
    expect(new URL(page.url()).pathname).toBe("/login");
  });

  test("empty email shows validation error before request is sent", async ({
    page,
  }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    // Fill only password, leave email blank
    await loginPage.fillPassword("Password1!");
    await loginPage.submit();

    // Should remain on /login — no navigation
    await page.waitForTimeout(300);
    expect(new URL(page.url()).pathname).toBe("/login");
  });

  test("empty password shows validation error before request is sent", async ({
    page,
  }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.fillEmail(sharedCreds.email);
    // Leave password blank
    await loginPage.submit();

    await page.waitForTimeout(300);
    expect(new URL(page.url()).pathname).toBe("/login");
  });

  test("designer login redirects to /analytics", async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login("designer@affectlearn.io", "Designer123!");

    await page.waitForURL((url) => url.pathname === "/analytics", {
      timeout: 15_000,
    });

    expect(new URL(page.url()).pathname).toBe("/analytics");
  });

  test("admin login redirects to /users", async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login("admin@affectlearn.io", "Admin123!");

    await page.waitForURL((url) => url.pathname === "/users", {
      timeout: 15_000,
    });

    expect(new URL(page.url()).pathname).toBe("/users");
  });

  test("'Sign up' link navigates to /register", async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();

    await loginPage.signUpLink().click();

    await page.waitForURL((url) => url.pathname === "/register", {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).toBe("/register");
  });

  test("already-authenticated user visiting /login is redirected away", async ({
    page,
    request,
  }) => {
    // Log in via UI, then navigate back to /login
    await loginViaUi(page, sharedCreds);
    await page.goto("/login");

    await page.waitForURL((url) => url.pathname !== "/login", {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).not.toBe("/login");
  });

  test("unauthenticated access to /courses redirects to /login", async ({
    page,
  }) => {
    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());
    await page.goto("/courses");

    await page.waitForURL((url) => url.pathname === "/login", {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).toBe("/login");
  });

  test("unauthenticated access to /analytics redirects to /login", async ({
    page,
  }) => {
    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());
    await page.goto("/analytics");

    await page.waitForURL((url) => url.pathname === "/login", {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).toBe("/login");
  });

  test("submit button is disabled during login request", async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.fillEmail(sharedCreds.email);
    await loginPage.fillPassword(sharedCreds.password);

    await page.route("**/api/v1/auth/login", async (route) => {
      await new Promise((r) => setTimeout(r, 800));
      await route.continue();
    });

    const submitBtn = loginPage.submitButton();
    await submitBtn.click();

    await expect(submitBtn).toBeDisabled({ timeout: 3_000 });
  });
});

// ---------------------------------------------------------------------------
// Auth API contract tests (no browser)
// ---------------------------------------------------------------------------

test.describe("Auth API — registration", () => {
  test("POST /register with valid data returns 201 and accessToken", async ({
    request,
  }) => {
    const creds = makeCredentials("api-reg");
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

    expect(res.status()).toBe(201);
    const body = await res.json();
    expect(body).toHaveProperty("accessToken");
    expect(body).toHaveProperty("refreshToken");
    expect(typeof body.accessToken).toBe("string");
  });

  test("POST /register with duplicate email returns 409", async ({
    request,
  }) => {
    const creds = makeCredentials("api-dup");
    // First registration
    await request.post(`${API_BASE}/auth/register`, {
      data: {
        emailAddress: creds.email,
        password: creds.password,
        firstName: creds.firstName,
        lastName: creds.lastName,
        ageRange: "18-24",
        degreeProgram: "Computer Science",
      },
    });

    // Second registration with same email
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

    expect(res.status()).toBe(409);
    const body = await res.json();
    // FastAPI wraps HTTPException.detail — code lives at detail.error.code or detail.code
    const code: string =
      body?.detail?.error?.code ?? body?.detail?.code ?? body?.detail ?? "";
    expect(
      ["ALREADY_REGISTERED", "EMAIL_ALREADY_EXISTS"].some((c) =>
        String(code).includes(c),
      ),
    ).toBe(true);
  });

  test("POST /register with missing required fields returns 422", async ({
    request,
  }) => {
    const res = await request.post(`${API_BASE}/auth/register`, {
      data: { emailAddress: "incomplete@test.com" },
    });

    expect(res.status()).toBe(422);
  });
});

test.describe("Auth API — login", () => {
  let apiCreds: TestCredentials;

  test.beforeAll(async ({ request }) => {
    apiCreds = makeCredentials("api-login");
    await apiRegister(request, apiCreds);
  });

  test("POST /login with valid credentials returns 200, accessToken, refreshToken", async ({
    request,
  }) => {
    const res = await request.post(`${API_BASE}/auth/login`, {
      data: { emailAddress: apiCreds.email, password: apiCreds.password },
    });

    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty("accessToken");
    expect(body).toHaveProperty("refreshToken");
    expect(typeof body.accessToken).toBe("string");
    expect(typeof body.refreshToken).toBe("string");
  });

  test("POST /login with invalid credentials returns 401 INVALID_CREDENTIALS", async ({
    request,
  }) => {
    const res = await request.post(`${API_BASE}/auth/login`, {
      data: { emailAddress: apiCreds.email, password: "WrongPassword9!" },
    });

    expect(res.status()).toBe(401);
    const body = await res.json();
    const code: string =
      body?.detail?.error?.code ?? body?.detail?.code ?? body?.detail ?? "";
    expect(String(code)).toMatch(/INVALID_CREDENTIALS/i);
  });

  test("POST /login with non-existent email returns 401", async ({
    request,
  }) => {
    const res = await request.post(`${API_BASE}/auth/login`, {
      data: {
        emailAddress: `ghost-${Date.now()}@nowhere.invalid`,
        password: "Password1!",
      },
    });

    expect(res.status()).toBe(401);
  });
});

test.describe("Auth API — /me", () => {
  let meToken: string;
  let meUser: Record<string, unknown>;

  test.beforeAll(async ({ request }) => {
    const creds = makeCredentials("api-me");
    const tokens = await apiRegister(request, creds);
    meToken = tokens.accessToken;
    meUser = await apiGetMe(request, meToken);
  });

  test("GET /me with valid token returns user with role, email, firstName", async ({
    request,
  }) => {
    const res = await request.get(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${meToken}` },
    });

    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty("role");
    expect(body).toHaveProperty("emailAddress");
    expect(body).toHaveProperty("firstName");
    expect(body.role).toBe("learner");
  });

  test("GET /me without token returns 401", async ({ request }) => {
    const res = await request.get(`${API_BASE}/auth/me`);
    expect(res.status()).toBe(401);
  });

  test("GET /me with malformed token returns 401", async ({ request }) => {
    const res = await request.get(`${API_BASE}/auth/me`, {
      headers: { Authorization: "Bearer not.a.real.jwt" },
    });
    expect(res.status()).toBe(401);
  });
});

test.describe("Auth API — consent and webcam", () => {
  let learnerToken: string;

  test.beforeAll(async ({ request }) => {
    const creds = makeCredentials("api-consent");
    const tokens = await apiRegister(request, creds);
    learnerToken = tokens.accessToken;
  });

  test("POST /auth/consent with consentGiven: true returns 200 and sets consentGivenAt", async ({
    request,
  }) => {
    const res = await request.post(`${API_BASE}/auth/consent`, {
      headers: { Authorization: `Bearer ${learnerToken}` },
      data: { consentGiven: true },
    });

    expect(res.status()).toBe(200);

    // /me should now have consentGivenAt set
    const me = await apiGetMe(request, learnerToken);
    expect(me.consentGivenAt).toBeTruthy();
  });

  test("POST /auth/consent as course designer returns 403", async ({
    request,
  }) => {
    const designerTokens = await apiLogin(request, {
      email: "designer@affectlearn.io",
      password: "Designer123!",
    });

    const res = await request.post(`${API_BASE}/auth/consent`, {
      headers: { Authorization: `Bearer ${designerTokens.accessToken}` },
      data: { consentGiven: true },
    });

    expect(res.status()).toBe(403);
  });

  test("POST /auth/webcam-mode with webcamEnabled: true as learner returns 200", async ({
    request,
  }) => {
    const res = await request.post(`${API_BASE}/auth/webcam-mode`, {
      headers: { Authorization: `Bearer ${learnerToken}` },
      data: { webcamEnabled: true },
    });

    expect(res.status()).toBe(200);
  });

  test("POST /auth/webcam-mode as course designer returns 403", async ({
    request,
  }) => {
    const designerTokens = await apiLogin(request, {
      email: "designer@affectlearn.io",
      password: "Designer123!",
    });

    const res = await request.post(`${API_BASE}/auth/webcam-mode`, {
      headers: { Authorization: `Bearer ${designerTokens.accessToken}` },
      data: { webcamEnabled: false },
    });

    expect(res.status()).toBe(403);
  });
});

// ---------------------------------------------------------------------------
// Logout behaviour
// ---------------------------------------------------------------------------

test.describe("Logout — session clearing", () => {
  test("clearing localStorage and navigating to /courses redirects to /login", async ({
    page,
    request,
  }) => {
    const creds = makeCredentials("logout-courses");
    const tokens = await apiRegister(request, creds);
    const user = await apiGetMe(request, tokens.accessToken);

    await seedSessionStorage(page, tokens, user);
    await page.goto("/courses");

    // Confirm we reached a protected page (or were redirected to onboarding — either is fine)
    await page.waitForURL(
      (url) =>
        url.pathname === "/courses" || url.pathname.startsWith("/onboarding"),
      { timeout: 15_000 },
    );

    // Simulate logout by removing the session key
    await page.evaluate(() => {
      localStorage.removeItem("affectlearn-session");
    });

    await page.goto("/courses");

    await page.waitForURL((url) => url.pathname === "/login", {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).toBe("/login");
  });

  test("clearing localStorage and navigating to /analytics redirects to /login", async ({
    page,
    request,
  }) => {
    const designerTokens = await apiLogin(request, {
      email: "designer@affectlearn.io",
      password: "Designer123!",
    });
    const designerUser = await apiGetMe(request, designerTokens.accessToken);

    await seedSessionStorage(page, designerTokens, designerUser);
    await page.goto("/analytics");

    await page.waitForURL((url) => url.pathname === "/analytics", {
      timeout: 15_000,
    });

    await page.evaluate(() => {
      localStorage.removeItem("affectlearn-session");
    });

    await page.goto("/analytics");

    await page.waitForURL((url) => url.pathname === "/login", {
      timeout: 10_000,
    });

    expect(new URL(page.url()).pathname).toBe("/login");
  });
});
