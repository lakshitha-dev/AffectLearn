/**
 * The two thesis figures that cannot be captured unattended: consent and webcam.
 *
 * WHY THIS FILE EXISTS SEPARATELY FROM THE OTHER TWO CAPTURE SPECS.
 *
 * `figures.spec.ts` captures these against a LOCAL instance, where seed data provides a
 * verified account. `figures-admin.spec.ts` captures the administrator views against a
 * DEPLOYED one. Neither can capture consent on a deployed instance, because:
 *
 *   - the consent step is only reachable by an account that has not yet consented, so an
 *     existing account is no use; and
 *   - `POST /auth/register` issues no tokens, and login is refused until the address is
 *     verified. The verification token is stored as a hash (`hash_url_token`), so it cannot
 *     be read back out of the database even with administrator access, and there is no
 *     administrator route that marks a user verified.
 *
 * So a person has to open the emailed link. That is the ONLY part that needs a person, and
 * this spec is built so it is the only part they do: it registers, waits for the click by
 * polling login, and then drives and captures both screens itself. Doing the screenshots by
 * hand instead would miss the viewport and scale the other figures use, and would not check
 * that the page is showing the copy the caption claims.
 *
 *   AL_BASE=https://affectlearn.tech \
 *   AL_API=https://affectlearn-api-2026.azurewebsites.net/api/v1 \
 *   AL_SIGNUP_EMAIL=you@example.com AL_SIGNUP_PASSWORD='...' \
 *   FIGURES=1 npx playwright test figures-onboarding --project=chromium --headed
 *
 * REAL CAMERA, DELIBERATELY. The existing webcam figure shows Chrome's synthetic test
 * pattern, a green rectangle with a rotating wedge, because the other specs pass
 * `--use-fake-device-for-media-stream`. That is right for an unattended run and wrong for a
 * figure captioned "the webcam step": a reader sees a broken preview. This spec passes
 * `--use-fake-ui-for-media-stream` only, which auto-accepts the permission prompt while
 * leaving the real device in place. Whoever runs it appears in Figure 3.16, so run it only
 * if you are content to be in the document, and set AL_FAKE_CAMERA=1 if you are not.
 *
 * The account is real and lives on production. The run prints its id and the exact command
 * to withdraw it; withdrawal erases the research rows the registration created.
 */

import { test, expect, type Page } from "@playwright/test";
import path from "node:path";

const BASE = process.env.AL_BASE || "http://localhost:3000";
const API = process.env.AL_API || "http://localhost:8000/api/v1";
const EMAIL = process.env.AL_SIGNUP_EMAIL || "";
const PASSWORD = process.env.AL_SIGNUP_PASSWORD || "";
const FAKE_CAMERA = process.env.AL_FAKE_CAMERA === "1";

const FIGURES = path.resolve(__dirname, "..", "..", "..", "docs", "thesis", "figures");
const EMAIL_RE = /[\w.+-]+@[\w-]+\.[\w.-]+/;

// Ten minutes to find an email, click a link, and come back. Generous on purpose: a person
// is in this loop and a spec that times out on a slow inbox wastes the whole run.
const VERIFY_TIMEOUT_MS = 10 * 60_000;
const POLL_MS = 5_000;

test.describe.configure({ mode: "serial", timeout: 15 * 60_000 });
test.skip(!process.env.FIGURES, "set FIGURES=1 to capture thesis figures");

test.use({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2, // the document scales figures to 4.5in; 1x reads as mush in print
  launchOptions: {
    args: FAKE_CAMERA
      ? ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]
      : ["--use-fake-ui-for-media-stream"],
  },
  permissions: ["camera"],
});

/**
 * Write one whole-viewport figure.
 *
 * The two guards are the ones `figures-admin.spec.ts` carries, and for the same reasons: an
 * earlier helper wrote a loading spinner over a good committed asset and reported success,
 * and a thesis figure must not carry anyone's email address. Consent and webcam are exactly
 * the screens where a registration address could appear.
 */
async function shot(page: Page, name: string) {
  const body = ((await page.locator("body").innerText()) || "").replace(/\s+/g, " ").trim();
  expect(body.length, `${name} is blank or still loading (${body.length} chars)`).toBeGreaterThan(200);
  const seen = body.match(EMAIL_RE);
  expect(seen, `an email address is visible on ${name}: ${seen?.[0]}`).toBeNull();
  await page.screenshot({ path: path.join(FIGURES, name), fullPage: false });
  console.log(`  wrote ${name}`);
}

test("consent and webcam steps on the deployed platform", async ({ page, request }) => {
  expect(EMAIL, "set AL_SIGNUP_EMAIL to an inbox you can open").not.toBe("");
  expect(PASSWORD, "set AL_SIGNUP_PASSWORD").not.toBe("");

  // --- register -------------------------------------------------------------
  const reg = await request.post(`${API}/auth/register`, {
    data: {
      emailAddress: EMAIL,
      password: PASSWORD,
      firstName: "Figure",
      lastName: "Capture",
    },
  });
  if (reg.status() === 409) {
    throw new Error(
      `${EMAIL} already has an account, and consent is only reachable by one that has not ` +
        `consented yet. Use a fresh address — most providers accept a +tag, e.g. ` +
        `you+figures@example.com — or withdraw the existing account first.`,
    );
  }
  expect(reg.status(), await reg.text()).toBe(201);

  console.log("\n  ────────────────────────────────────────────────────────────");
  console.log(`  Registered ${EMAIL}.`);
  console.log("  OPEN YOUR INBOX AND CLICK THE VERIFICATION LINK NOW.");
  console.log("  This run continues on its own the moment you do.");
  console.log("  ────────────────────────────────────────────────────────────\n");

  // --- wait for the human ---------------------------------------------------
  // Polling login rather than asking for a keypress: the click IS the signal, so there is
  // nothing to confirm and no way to continue too early.
  const deadline = Date.now() + VERIFY_TIMEOUT_MS;
  let tokens: { accessToken: string; refreshToken?: string; expiresIn?: number } | null = null;
  while (Date.now() < deadline) {
    const r = await request.post(`${API}/auth/login`, {
      data: { emailAddress: EMAIL, password: PASSWORD },
    });
    if (r.ok()) {
      tokens = await r.json();
      break;
    }
    await new Promise((r2) => setTimeout(r2, POLL_MS));
  }
  expect(tokens, `no verification within ${VERIFY_TIMEOUT_MS / 60_000} minutes`).not.toBeNull();
  console.log("  verified — continuing\n");

  const me = await request.get(`${API}/auth/me`, {
    headers: { Authorization: `Bearer ${tokens!.accessToken}` },
  });
  expect(me.ok()).toBeTruthy();
  const user = await me.json();

  // --- put the session where the app expects it -----------------------------
  // Shape and key copied from `helpers/auth.ts:seedSessionStorage`, which cannot be reused
  // here because its API_BASE is hardcoded to localhost. `addInitScript` rather than
  // `evaluate`: the auth guard reads this on mount and renders a spinner until it is there,
  // so writing it after navigation is a race the capture would sometimes lose.
  await page.addInitScript(
    (serialised) => localStorage.setItem("affectlearn-session", serialised),
    JSON.stringify({
      state: {
        accessToken: tokens!.accessToken,
        refreshToken: tokens!.refreshToken,
        expiresAt: Date.now() + (tokens!.expiresIn ?? 3600) * 1000,
        user,
      },
      version: 0,
    }),
  );

  // --- consent --------------------------------------------------------------
  await page.goto(`${BASE}/onboarding`, { waitUntil: "domcontentloaded", timeout: 90_000 });
  await page.getByRole("button", { name: /get started|continue|next/i }).first().click();

  await expect(page.getByRole("heading", { name: /consent/i })).toBeVisible({ timeout: 60_000 });
  // The guard is on the CURRENT privacy sentence. A capture of the superseded "frames are
  // never stored" copy is the thing this whole exercise exists to replace, so writing one
  // would be worse than writing nothing.
  await expect(
    page.getByText(/ever leaves?|never leaves?|no image|not transmitted/i).first(),
  ).toBeVisible({ timeout: 30_000 });
  // Captured before the box is ticked: Figure 3.15's caption claims the "I agree" button is
  // blocked until it is, and the disabled button has to be visible for that to be evidenced.
  await shot(page, "figshot-consent.png");

  // --- webcam ---------------------------------------------------------------
  await page.getByRole("checkbox").first().check();
  await page.getByRole("button", { name: /agree|continue|next/i }).first().click();

  await expect(page.getByRole("heading", { name: /webcam|camera/i })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/leave your computer|never sent|only measurements/i).first())
    .toBeVisible({ timeout: 30_000 });
  // The preview needs a moment to attach the stream; an empty <video> is a worse figure than
  // the synthetic pattern it replaces.
  await page.waitForTimeout(4_000);
  await shot(page, "figshot-webcam.png");

  console.log("\n  ────────────────────────────────────────────────────────────");
  console.log("  Both figures written. Now remove the account from production:");
  console.log(`    POST ${API}/admin/users/${user.id}/withdraw   (as an administrator)`);
  console.log("  ────────────────────────────────────────────────────────────\n");
});
