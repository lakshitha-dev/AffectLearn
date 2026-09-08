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

/** Full-page capture, refusing if the page shows an identifier a thesis must not print. */
async function shotPage(page: Page, name: string) {
  const body = (await page.locator("body").innerText()).replace(/\s+/g, " ");
  const hit = body.match(EMAIL_RE);
  expect(hit, `an email address is visible on ${name}: ${hit?.[0] ?? ""}`).toBeNull();
  await page.screenshot({ path: path.join(FIGURES, name), fullPage: true });
  console.log(`  wrote ${name}`);
}

/** Navigate without waiting on `load`, which the admin shell never settles. */
async function open(page: Page, route: string) {
  await page.goto(route, { waitUntil: "domcontentloaded", timeout: 90_000 });
  // The auth guard renders a spinner until the persisted session rehydrates.
  await page.waitForFunction(
    () => !!localStorage.getItem("affectlearn-session"),
    null, { timeout: 30_000 });
}


async function whole(page: Page, name: string) {
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
