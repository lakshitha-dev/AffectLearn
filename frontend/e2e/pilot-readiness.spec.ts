/**
 * Pilot readiness check -- run before EACH pilot day, against the local pilot stack.
 *
 * This is an automated SYSTEM TEST, not data collection. It signs in as the demo-flagged
 * readiness account (created by `scripts/create_pilot_participants.py --readiness`), which every
 * research export excludes, and drives one lesson with Chromium's FAKE camera. The fake camera is
 * used here and nowhere else: participants use their real webcam in a normal Chrome window.
 *
 * It fails loudly if any of these is not true:
 *   1. the pipeline is healthy and runs the frozen pilot configuration (geometry facial model,
 *      GBDT behavioural model, floors 0.70, bored/confused, fusion advisory, no withholding);
 *   2. the browser sends a facial and a behavioural window within ~70 s;
 *   3. those windows reach Postgres as research events carrying `eventId` and `decisionId`,
 *      alongside a `session_provenance` event and a raw interaction window.
 *
 *   PILOT_READINESS=1 \
 *   PILOT_READINESS_EMAIL=readiness@pilot.invalid PILOT_READINESS_PASSWORD=... \
 *   PILOT_ADMIN_PASSWORD=... \
 *   npx playwright test e2e/pilot-readiness.spec.ts
 */

import { test, expect, type APIRequestContext } from "@playwright/test";

import {
  API_BASE,
  apiEnroll,
  apiGetMe,
  apiLogin,
  getCourseDetail,
  getFirstCourseId,
  seedSessionStorage,
} from "./helpers/auth";

const ENABLED = process.env.PILOT_READINESS === "1";
const READY = {
  email: process.env.PILOT_READINESS_EMAIL ?? "readiness@pilot.invalid",
  password: process.env.PILOT_READINESS_PASSWORD ?? "",
};
const ADMIN = {
  email: process.env.PILOT_ADMIN_EMAIL ?? "admin@affectlearn.io",
  password: process.env.PILOT_ADMIN_PASSWORD ?? "",
};

test.skip(!ENABLED, "set PILOT_READINESS=1 to run the pilot readiness check");

test.use({
  launchOptions: {
    args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
  },
  permissions: ["camera"],
});

test.describe.configure({ timeout: 180_000 });

async function authed(request: APIRequestContext, token: string, path: string) {
  const res = await request.get(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(res.ok(), `GET ${path} -> ${res.status()}`).toBeTruthy();
  return res.json();
}

test("the pipeline runs the frozen pilot configuration", async ({ request }) => {
  const health = await (await request.get(API_BASE.replace("/api/v1", "") + "/health/pipeline")).json();
  expect(health.status).toBe("ok");
  expect(health.models.facial.kind).toBe("geometry");
  expect(health.models.facial.exists).toBe(true);
  expect(health.models.behavioral.path).toContain("behavioral_confusion_gbdt");
  expect(health.models.decision.adaptStates).toEqual(["bored", "confused"]);
  expect(health.models.decision.fusionDrivesDecision).toBe(false);
  expect(health.models.decision.channelMinConfidence.facial_geometry).toBe(0.7);

  const admin = await apiLogin(request, ADMIN);
  const config = await authed(request, admin.accessToken, "/admin/config");
  expect(config.values.withholdRate).toBe(0);
  expect(config.values.minConfidence).toBe(0.7);
  // Locking is the last step before the first participant: warn, do not fail, before then.
  expect.soft(config.locked, "config is not locked yet (POST /admin/config/lock)").toBe(true);
});

test("a lesson's windows reach the research record with their identities", async ({
  page,
  request,
}) => {
  const tokens = await apiLogin(request, READY);
  const user = await apiGetMe(request, tokens.accessToken);
  expect(user.consentGivenAt, "readiness account must be consented").toBeTruthy();
  expect(user.webcamEnabled).toBe(true);

  const courseId = process.env.PILOT_COURSE_ID ?? (await getFirstCourseId(request, tokens.accessToken));
  await apiEnroll(request, tokens.accessToken, courseId).catch(() => undefined); // already enrolled
  const course = await getCourseDetail(request, tokens.accessToken, courseId);
  const lesson = course.modules[0]?.lessons[0];
  expect(lesson, "the pilot course has no lessons -- seed it first").toBeTruthy();

  const sent = new Set<string>();
  page.on("websocket", (ws) =>
    ws.on("framesent", (frame) => {
      if (typeof frame.payload !== "string") return;
      try {
        sent.add(JSON.parse(frame.payload).type);
      } catch {
        /* not JSON */
      }
    }),
  );

  const startedAt = Date.now();
  await seedSessionStorage(page, tokens, user);
  await page.goto(`/courses/${courseId}/modules/${course.modules[0].id}/lessons/${lesson!.id}`);
  // Something to capture: a little pointer movement and a scroll.
  for (let i = 0; i < 20; i += 1) await page.mouse.move(200 + i * 10, 300 + i * 5);
  await page.mouse.wheel(0, 400);

  await expect
    .poll(() => sent.has("facial_features") && sent.has("behavioral_window"), {
      timeout: 75_000, intervals: [2_000],
    })
    .toBe(true);

  // The worker drains the stream about once a second; give it a few.
  await expect
    .poll(async () => {
      const dump = await authed(request, tokens.accessToken, "/auth/me/export");
      const events = (dump.researchEvents ?? []).filter(
        (e: { timestamp: number }) => e.timestamp >= startedAt,
      );
      const types = new Set(events.map((e: { eventType: string }) => e.eventType));
      const identified = events.every((e: { eventId?: string }) => Boolean(e.eventId));
      const traced = events
        .filter((e: { eventType: string }) =>
          ["facial_affect_detected", "behavioral_affect_detected"].includes(e.eventType))
        .every((e: { decisionId?: string }) => Boolean(e.decisionId));
      const raw = (dump.rawInteractionWindows ?? []).length > 0;
      return (
        types.has("session_provenance") &&
        types.has("facial_affect_detected") &&
        types.has("behavioral_affect_detected") &&
        identified && traced && raw
      );
    }, { timeout: 30_000, intervals: [3_000] })
    .toBe(true);
});
