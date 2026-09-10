/**
 * Administrator-side thesis figures, captured against a running instance while a
 * learner drives the other side by hand.
 *
 * `figures.spec.ts` drives both sides itself, which is the right tool when the
 * captures only have to be self-consistent. It is the wrong tool when a real
 * person is in the session: a synthetic learner cannot produce the behaviour the
 * monitor is interesting for. This file captures the administrator side only and
 * expects someone to be learning at the same time.
 *
 * Point it at whichever instance the learner is using:
 *
 *   AL_BASE=https://affectlearn.tech \
 *   AL_API=https://affectlearn-api-2026.azurewebsites.net/api/v1 \
 *   AL_ADMIN_EMAIL=... AL_ADMIN_PASSWORD=... \
 *   FIGURES=1 npx playwright test figures-admin --project=chromium
 *
 * Credentials come from the environment and are never written to disk. Run it
 * repeatedly: each run overwrites the captures, so the last run while the
 * learner is still in the session is the one that lands in the document.
 *
 * PRIVACY. The monitor identifies sessions by opaque identifiers, but the user
 * table on `/users` and the session picker can carry a real name or email. This
 * file does not visit `/users`, and it fails rather than capturing if an email
 * address is visible in a panel it is about to shoot, because a thesis figure
 * must not carry a participant's identity.
 */

import { test, expect, type Page } from "@playwright/test";
import path from "node:path";

const BASE = process.env.AL_BASE ?? "http://localhost:3000";
const API = process.env.AL_API ?? "http://localhost:8000/api/v1";
const EMAIL = process.env.AL_ADMIN_EMAIL ?? "";
const PASSWORD = process.env.AL_ADMIN_PASSWORD ?? "";

const FIGURES = path.resolve(
  __dirname, "..", "..", "..", "docs", "thesis", "figures",
);

const EMAIL_RE = /[\w.+-]+@[\w-]+\.[\w.-]+/;

test.describe.configure({ mode: "serial", timeout: 4 * 60_000 });
test.skip(!process.env.FIGURES, "set FIGURES=1 to capture thesis figures");

test.use({
  baseURL: BASE,
  viewport: { width: 1600, height: 1000 },
  deviceScaleFactor: 2,
});

/** Log in through the API and seed the session store, as the helpers do. */
async function asAdmin(page: Page, request: import("@playwright/test").APIRequestContext) {
  expect(EMAIL, "set AL_ADMIN_EMAIL").not.toBe("");
  expect(PASSWORD, "set AL_ADMIN_PASSWORD").not.toBe("");

  const res = await request.post(`${API}/auth/login`, {
    data: { emailAddress: EMAIL, password: PASSWORD },
  });
  expect(res.ok(), `login failed (${res.status()})`).toBeTruthy();
  const tokens = await res.json();

  const me = await request.get(`${API}/auth/me`, {
    headers: { Authorization: `Bearer ${tokens.accessToken}` },
  });
  expect(me.ok(), "could not read the admin profile").toBeTruthy();
  const user = await me.json();

  const state = JSON.stringify({
    state: {
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
      expiresAt: Date.now() + tokens.expiresIn * 1000,
      user,
    },
    version: 0,
  });
  await page.addInitScript((s) => {
    localStorage.setItem("affectlearn-session", s);
  }, state);
}

/** Full-page capture, refusing to write a page that is blank or carries an identifier.
 *
 * The blank check is not defensive padding. An earlier version of this helper wrote a
 * loading spinner over a good committed asset and reported success, because it only
 * looked for email addresses. A capture that cannot see content must fail: a missing
 * figure is caught by `check_submission.py`, a blank one is not.
 */
async function shotPage(page: Page, name: string) {
  const body = (await page.locator("body").innerText()).replace(/\s+/g, " ").trim();
  expect(body.length, `${name} is blank or still loading (${body.length} chars of text)`)
    .toBeGreaterThan(200);
  const hit = body.match(EMAIL_RE);
  expect(hit, `an email address is visible on ${name}: ${hit?.[0] ?? ""}`).toBeNull();
  await page.screenshot({ path: path.join(FIGURES, name), fullPage: true });
  console.log(`  wrote ${name} (${body.length} chars of text)`);
}

/** Navigate without waiting on `load`, which the admin shell never settles. */
async function open(page: Page, route: string) {
  await page.goto(route, { waitUntil: "domcontentloaded", timeout: 90_000 });
  // The auth guard renders a spinner until the persisted session rehydrates.
  await page.waitForFunction(
    () => !!localStorage.getItem("affectlearn-session"),
    null, { timeout: 30_000 });
}


// Viewport rather than full page. The monitor is several screens tall, and a figure of
// the whole thing renders the configuration banner as one unreadable line; the banner is
// the point of that figure, so it is captured at the top of the viewport instead.
async function viewport(page: Page, name: string) {
  const body = ((await page.locator("body").innerText()) || "").replace(/\s+/g, " ").trim();
  expect(body.length, `${name} is blank or still loading`).toBeGreaterThan(200);
  const seen = body.match(EMAIL_RE);
  expect(seen, `an email address is visible on ${name}: ${seen?.[0]}`).toBeNull();
  await page.screenshot({ path: path.join(FIGURES, name), fullPage: false });
  console.log(`  wrote ${name}`);
}

// ---------------------------------------------------------------------------

test("pipeline monitor during a live learner session", async ({ page, request }) => {
  await asAdmin(page, request);
  await open(page, "/monitor");

  // The banner is the load-bearing content: it evidences that the facial channel
  // is the geometric one and which floor each channel is held to.
  await expect(page.getByText(/facial:\s*geometry/i)).toBeVisible({ timeout: 60_000 });
  await viewport(page, "figshot-monitor-config.png");
  // Give the live panels a cycle to populate before capturing.
  await page.waitForTimeout(8_000);
  await shotPage(page, "figshot-monitor-live.png");
});

test("monitor aggregate view", async ({ page, request }) => {
  await asAdmin(page, request);
  await open(page, "/monitor");
  const tab = page.getByRole("tab", { name: /aggregate/i });
  await expect(tab).toBeVisible({ timeout: 45_000 });
  await tab.click();
  await expect(page.getByText(/why cycles did not adapt/i)).toBeVisible({ timeout: 45_000 });

  // Thirty days, because that is the window the deployment record is reported over.
  // The 24-hour default shows an empty chart on an instance nobody used yesterday,
  // which evidences nothing and reads as a broken page.
  // By its aria-label, not by position: the first combobox on the page is the session
  // picker, and selecting a window from that one silently picks a session instead.
  const window = page.getByRole("combobox", { name: /aggregation window/i });
  if (await window.isVisible().catch(() => false)) {
    await window.click();
    const thirty = page.getByRole("option", { name: /30 days/i });
    // Tolerant on purpose: the option only exists on a frontend carrying the widened
    // WINDOWS list, and a capture run against an older deploy should fall back rather
    // than fail. The assertion below pins whichever window was actually selected.
    if (await thirty.isVisible().catch(() => false)) {
      await thirty.click();
      await expect(page.getByText(/window: 720h/i)).toBeVisible({ timeout: 45_000 });
    } else {
      await page.getByRole("option", { name: /7 days/i }).click();
      await expect(page.getByText(/window: 168h/i)).toBeVisible({ timeout: 45_000 });
    }
  }
  await shotPage(page, "figshot-monitor-aggregate.png");
});

test("system health, models and gate configuration", async ({ page, request }) => {
  await asAdmin(page, request);
  await open(page, "/system-health");
  // This is the figure that proves which artefacts are loaded, so both paths
  // have to be on screen before it is worth taking.
  await expect(page.getByText(/engagenet_lean_gbdt/i)).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText(/behavioral_confusion_gbdt/i)).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText(/behavioral_bilstm/i)).toHaveCount(0);
  await shotPage(page, "figshot-system-health.png");
});

test("course-designer affect view", async ({ page, request }) => {
  await asAdmin(page, request);
  const res = await request.get(`${API}/courses?page=1&pageSize=1`);
  const courseId = res.ok() ? (await res.json()).items?.[0]?.id : null;
  test.skip(!courseId, "no published course to read analytics for");

  await open(page, `/analytics/${courseId}`);
  await expect(page.getByRole("grid")).toBeVisible({ timeout: 45_000 });
  await shotPage(page, "figshot-heatmap.png");
});

// ---------------------------------------------------------------------------
// The onboarding screens are deliberately NOT captured here.
//
// The consent copy changed when the geometric channel replaced the pixel one,
// from "frames are never stored" to "no image is transmitted", so the capture in
// the thesis promises something weaker than the platform now does and should be
// redone. It cannot be automated against a deployed instance: `POST /auth/register`
// issues no tokens because login is gated on email verification, and the consent
// step is only reachable by an account that has not yet consented. Verifying an
// address needs the emailed link, and engineering around that on production is not
// something a figure is worth.
//
// So it needs a person: register, verify, and capture the consent and webcam steps
// before agreeing. `figures.spec.ts` does it unattended against a local instance,
// where the seed data provides a verified account.
// ---------------------------------------------------------------------------
