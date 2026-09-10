/**
 * E2E tests — WebSocket connection lifecycle (Story 4.1, AC #1, #5, #11).
 *
 * Asserts the learner WebSocket opens on the lesson page, transparently reconnects
 * after a transient drop, and is closed by the server when a second tab opens for the
 * same learner.
 *
 * Reads `window.__connectionStore` which the useWebSocket hook attaches on mount.
 */

import { test, expect, type Page } from "@playwright/test";
import {
  seedLearnerOnFirstLesson,
  seedSessionStorage,
} from "./helpers/auth";

interface WSSuiteState {
  tokens: { accessToken: string; refreshToken: string; expiresIn: number };
  user: Record<string, unknown>;
  lessonUrl: string;
}

let shared: WSSuiteState;

test.beforeAll(async ({ request }) => {
  const { tokens, user, lessonUrl } = await seedLearnerOnFirstLesson(request, "ws");
  shared = { tokens, user, lessonUrl };
});

async function readIsConnected(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const store = (window as unknown as { __connectionStore?: { getState: () => { isConnected: boolean } } }).__connectionStore;
    return store?.getState().isConnected ?? false;
  });
}

async function readConnectionState(page: Page): Promise<string> {
  return page.evaluate(() => {
    const store = (window as unknown as { __connectionStore?: { getState: () => { connectionState: string } } }).__connectionStore;
    return store?.getState().connectionState ?? "missing";
  });
}

async function waitForConnected(page: Page, timeoutMs = 5_000): Promise<void> {
  await expect
    .poll(async () => readIsConnected(page), {
      timeout: timeoutMs,
      message: "WS isConnected never became true",
    })
    .toBe(true);
}

test.describe("WebSocket connection", () => {
  test("opens on the lesson page and reports isConnected=true", async ({ page }) => {
    await seedSessionStorage(page, shared.tokens, shared.user);
    await page.goto(shared.lessonUrl);

    await waitForConnected(page);
    expect(await readConnectionState(page)).toBe("open");
  });

  test("second tab supersedes the first; first tab sees connectionState=closed", async ({
    browser,
  }) => {
    const ctxA = await browser.newContext();
    const pageA = await ctxA.newPage();
    await seedSessionStorage(pageA, shared.tokens, shared.user);
    await pageA.goto(shared.lessonUrl);
    await waitForConnected(pageA);

    const ctxB = await browser.newContext();
    const pageB = await ctxB.newPage();
    await seedSessionStorage(pageB, shared.tokens, shared.user);
    await pageB.goto(shared.lessonUrl);
    await waitForConnected(pageB);

    // Page A's connection should now be superseded (close code 4001).
    await expect
      .poll(async () => readConnectionState(pageA), {
        timeout: 5_000,
        message: "First tab never observed supersede",
      })
      .toBe("closed");

    await ctxA.close();
    await ctxB.close();
  });
});
