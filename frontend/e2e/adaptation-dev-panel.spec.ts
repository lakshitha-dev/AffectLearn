/**
 * E2E — the adaptation trigger panel, in both of its modes.
 *
 * SKIPPED unless the frontend was started with `NEXT_PUBLIC_AFFECT_DEBUG=1`, which is how the two
 * existing debug overlays are gated too. Skipped rather than failed: the panel being absent from a
 * normal build is the correct behaviour, and a red test for it would train people to ignore this
 * file.
 *
 * The panel is how anyone sees the five adaptation types the product cannot produce on demand, so
 * "the panel is broken" and "the loop is broken" must not look the same. This asserts both of its
 * modes separately: RENDER puts a card on screen with no backend involved, and LOOP reports what
 * the real graph decided and whether it reached the socket.
 */

import { test, expect } from "@playwright/test";

import { seedLearnerOnFirstLesson, seedSessionStorage } from "./helpers/auth";

test("the dev panel renders a card and drives the real loop", async ({ page, request }) => {
  // The loop calls a language model that is not configured here, so it waits out the timeout and
  // falls back to the rule ladder. That is a real path, and it is slow.
  test.setTimeout(90_000);

  const { tokens, user, lessonUrl } = await seedLearnerOnFirstLesson(request, "panel");
  await seedSessionStorage(page, tokens, user);
  await page.goto(lessonUrl);

  const opener = page.getByRole("button", { name: "Adaptation harness" });
  // Waited for, not counted: the panel is client-rendered and `count()` does not auto-wait, so a
  // bare count races the hydration and skips a panel that is about to appear.
  const present = await opener
    .waitFor({ state: "visible", timeout: 20_000 })
    .then(() => true)
    .catch(() => false);
  test.skip(!present, "Panel is gated on NEXT_PUBLIC_AFFECT_DEBUG=1; not set for this run.");
  await opener.click();

  // RENDER — store only, no socket, no decision.
  await page.locator("tr", { hasText: "show_breakdown" }).getByText("render").click();
  await expect(page.getByText("Let's break this down")).toBeVisible();

  // LOOP — the compiled graph, the live gate, and a push down the WebSocket.
  await page.locator("tr", { hasText: "show_hint" }).getByText("loop").click();
  const verdict = page.getByText("on screen").locator("..");
  await expect(verdict).toContainText("yes", { timeout: 60_000 });
});
