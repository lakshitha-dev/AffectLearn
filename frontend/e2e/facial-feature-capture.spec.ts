/**
 * E2E — Client-side facial feature capture (Story 4.2).
 *
 * Scope: verifies the privacy + inertness contracts on the real browser. The
 * "adaptive-mode happy path" (face detected, frame sent) is covered by the
 * unit tests (`use-media-pipe.test.ts`) — exercising it in E2E would need a
 * Y4M sample with a real face plus webcam-store manipulation across the
 * onboarding boundary, both out of scope for this story.
 *
 * What this spec asserts:
 *   - AC #7: A freshly-registered learner (default `webcamEnabled: false`,
 *     webcam-store mode === "behavioral") visits a lesson page → NO
 *     `facial_features` traffic is emitted on the WebSocket.
 *   - AC #10: No facial-data keys land in localStorage / sessionStorage.
 *
 * Chrome is launched with `--use-fake-device-for-media-stream` so any
 * `getUserMedia` call (which AC #7 forbids in behavioral mode) would
 * still succeed silently rather than block the test on a permission dialog.
 */

import { test, expect } from "@playwright/test";
import {
  apiEnroll,
  apiGetMe,
  apiRegister,
  getCourseDetail,
  getFirstCourseId,
  makeCredentials,
  seedSessionStorage,
} from "./helpers/auth";

test.use({
  launchOptions: {
    args: [
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
    ],
  },
  permissions: ["camera"],
});

interface SuiteState {
  tokens: { accessToken: string; refreshToken: string; expiresIn: number };
  user: Record<string, unknown>;
  lessonUrl: string;
}

let shared: SuiteState;

test.beforeAll(async ({ request }) => {
  const creds = makeCredentials("fc");
  const tokens = await apiRegister(request, creds);
  const user = await apiGetMe(request, tokens.accessToken);
  const courseId = await getFirstCourseId(request, tokens.accessToken);
  await apiEnroll(request, tokens.accessToken, courseId);

  const course = await getCourseDetail(request, tokens.accessToken, courseId);
  const firstModule = course.modules[0];
  if (!firstModule) throw new Error("Test course has no modules — seed the database first.");
  const firstLesson = firstModule.lessons[0];
  if (!firstLesson) throw new Error("First module has no lessons — seed the database first.");

  shared = {
    tokens,
    user,
    lessonUrl: `/courses/${courseId}/modules/${firstModule.id}/lessons/${firstLesson.id}`,
  };
});

test.describe("Facial feature capture", () => {
  test("AC #7 — behavioral-mode learner emits no facial_features frames", async ({ page }) => {
    await seedSessionStorage(page, shared.tokens, shared.user);

    const sentFrames: string[] = [];
    page.on("websocket", (ws) => {
      ws.on("framesent", (frame) => {
        if (typeof frame.payload === "string") sentFrames.push(frame.payload);
      });
    });

    await page.goto(shared.lessonUrl);
    await page.waitForTimeout(5_000);

    const facialFrames = sentFrames.filter((p) =>
      p.includes('"facial_features"'),
    );
    expect(facialFrames.length).toBe(0);
  });

  test("AC #10 — no facial-data keys in localStorage or sessionStorage", async ({
    page,
  }) => {
    await seedSessionStorage(page, shared.tokens, shared.user);
    await page.goto(shared.lessonUrl);
    await page.waitForTimeout(3_000);

    const facialKeys = await page.evaluate(() => {
      const all = [...Object.keys(localStorage), ...Object.keys(sessionStorage)];
      return all.filter((k) =>
        /face|facial|frame|media[-_ ]?pipe|webcam[-_ ]?frames/i.test(k),
      );
    });

    expect(facialKeys).toEqual([]);
  });
});
