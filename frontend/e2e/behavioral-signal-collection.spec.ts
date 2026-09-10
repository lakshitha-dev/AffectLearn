/**
 * E2E — Client-side behavioral signal collection (Story 4.3).
 *
 * Scope: verifies the real-browser contracts that the unit tests
 * (`use-behavioral-signals.test.ts`) cannot — that a behavioral-mode learner
 * actually emits a `behavioral_window` message over the live WebSocket, that it
 * conforms to the AC #4 schema, and that typed keystroke content never appears
 * on the wire (AC #6).
 *
 * Timing note: the production cycle is locked at 30s (NOT overridable from the
 * page), so this test waits ~32s for the first window. The per-test timeout is
 * raised accordingly. Both structure and privacy are asserted from the SAME
 * captured window to avoid a second 30s wait.
 *
 * Requires the backend (localhost:8000) and a seeded course, same as the
 * facial-feature-capture spec.
 */

import { test, expect } from "@playwright/test";
import {
  seedLearnerOnFirstLesson,
  seedSessionStorage,
} from "./helpers/auth";

interface SuiteState {
  tokens: { accessToken: string; refreshToken: string; expiresIn: number };
  user: Record<string, unknown>;
  lessonUrl: string;
}

let shared: SuiteState;

test.beforeAll(async ({ request }) => {
  // Default webcamEnabled=false → webcam-store mode === "behavioral".
  const { tokens, user, lessonUrl } = await seedLearnerOnFirstLesson(request, "bsc");
  shared = { tokens, user, lessonUrl };
});

test.describe("Behavioral signal collection", () => {
  test("AC #4 + #6 — emits a schema-conformant behavioral_window with no keystroke content", async ({
    page,
  }) => {
    // A full 30s cycle plus navigation + margin.
    test.setTimeout(60_000);

    await seedSessionStorage(page, shared.tokens, shared.user);

    const sentFrames: string[] = [];
    page.on("websocket", (ws) => {
      ws.on("framesent", (frame) => {
        if (typeof frame.payload === "string") sentFrames.push(frame.payload);
      });
    });

    await page.goto(shared.lessonUrl);

    // Type a sensitive string — the global keydown listener captures category only.
    await page.keyboard.type("SECRET123");

    // Wait for the first 30s cycle boundary to fire (+ margin).
    await page.waitForTimeout(32_000);

    const behavioralFrames = sentFrames.filter((p) =>
      p.includes('"behavioral_window"'),
    );
    expect(behavioralFrames.length).toBeGreaterThanOrEqual(1);

    const payload = JSON.parse(behavioralFrames[0]);
    expect(payload.type).toBe("behavioral_window");
    expect(typeof payload.ts).toBe("number");
    expect(payload.data.window_duration_ms).toBe(30_000);
    expect(payload.data.sampling_rate_hz).toBe(10);
    expect(payload.data.schema_version).toBe(1);
    expect(payload.data.cycle_number).toBeGreaterThanOrEqual(1);
    expect(Array.isArray(payload.data.events)).toBe(true);
    expect(payload.data.summary).toBeDefined();
    expect(typeof payload.data.summary.idle).toBe("boolean");

    // AC #6: no keystroke content anywhere in any sent behavioral frame.
    for (const frame of behavioralFrames) {
      for (const ch of "SECRET") {
        expect(frame).not.toContain(ch);
      }
    }
  });
});
