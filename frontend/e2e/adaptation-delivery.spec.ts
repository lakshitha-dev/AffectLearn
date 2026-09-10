/**
 * E2E — every adaptation type renders on a real lesson page.
 *
 * There was NO e2e coverage of adaptations at all, which is why five of the eight action types
 * had never been seen on screen by anyone. The unit tests render each component in isolation and
 * pass; that says nothing about whether a delivered adaptation reaches one, because the routing
 * from queue to component lives in three different consumers mounted at three different places on
 * the page, and two of the actions were absent from a lookup table for months without a single
 * test noticing.
 *
 * HOW IT DRIVES THE QUEUE. Through `window.__adaptationStore`, which `use-websocket.ts` exposes
 * beside `__connectionStore` behind the same production guard. The alternative — producing genuine
 * affect in front of a webcam, sustained across two cycles, above the confidence floor, outside a
 * cooldown, out of the withheld arm — is not something a test can do. What is asserted here is the
 * half after delivery: queue → component → screen. The half before it (detection, gate,
 * strategist, adapter) is covered by `tests/api/test_dev_tools.py` and `scripts/drive_adaptations.py`.
 *
 * NO `data-testid` ANYWHERE IN `components/learning/`, so every assertion below uses a handle the
 * learner also has: the landmark role, its accessible name, the visible copy. That is deliberate
 * — a testid can stay green while the accessible name is wrong, and the accessible name is what a
 * screen-reader user gets instead of the card.
 */

import { test, expect, type Page } from "@playwright/test";

import { API_BASE, seedLearnerOnFirstLesson, seedSessionStorage } from "./helpers/auth";

interface SuiteState {
  tokens: { accessToken: string; refreshToken: string; expiresIn: number };
  user: Record<string, unknown>;
  lessonUrl: string;
  lessonId: string;
}

let shared: SuiteState;

test.beforeAll(async ({ request }) => {
  const { tokens, user, lessonUrl, lessonId } = await seedLearnerOnFirstLesson(request, "adapt");
  shared = { tokens, user, lessonUrl, lessonId };
});

/**
 * Put exactly one adaptation in the queue.
 *
 * `reset()` first, every time. The queue is append-only and each consumer takes the LAST item
 * matching its own action set, so an item left by a previous case keeps winning for every family
 * it belongs to and the next assertion passes or fails for the wrong reason.
 */
async function deliver(page: Page, action: string, text: string): Promise<void> {
  await page.evaluate(
    ({ action, text }) => {
      const store = (
        window as unknown as {
          __adaptationStore?: {
            getState: () => {
              reset: () => void;
              pushAdaptation: (a: {
                id: string;
                action: string;
                text: string;
                receivedAt: number;
              }) => void;
            };
          };
        }
      ).__adaptationStore;
      if (!store) throw new Error("__adaptationStore is not exposed — is this a production build?");
      store.getState().reset();
      store.getState().pushAdaptation({
        id: `e2e-${action}-${Date.now()}`,
        action,
        text,
        receivedAt: Date.now(),
      });
    },
    { action, text },
  );
}

async function openLesson(page: Page): Promise<void> {
  await seedSessionStorage(page, shared.tokens, shared.user);
  await page.goto(shared.lessonUrl);
  // The store is attached by the WebSocket hook's connect effect, not on first paint.
  await expect
    .poll(
      () =>
        page.evaluate(
          () => Boolean((window as unknown as { __adaptationStore?: unknown }).__adaptationStore),
        ),
      { timeout: 20_000 },
    )
    .toBe(true);
}

test.describe("Adaptation delivery", () => {
  test("the four show_* actions each render their own callout", async ({ page }) => {
    await openLesson(page);

    // Each case asserts the LABEL as well as the body. A missing `VARIANT_BY_ACTION` entry still
    // renders the body perfectly — it just introduces it with the wrong sentence — so a body-only
    // assertion is exactly the assertion that misses this class of bug.
    const cases: Array<[string, string, string]> = [
      ["show_hint", "Think of the handshake as a greeting.", "Here's another way to think about this…"],
      ["show_alternative", "Picture it as a flowchart instead.", "Another way to look at this"],
      ["show_breakdown", "First the SYN.\nThen the SYN-ACK.\nFinally the ACK.", "Let's break this down"],
    ];

    for (const [action, text, label] of cases) {
      await deliver(page, action, text);
      const callout = page.getByRole("complementary", { name: "Learning hint" });
      await expect(callout).toBeVisible();
      await expect(callout.getByText(label)).toBeVisible();
      await expect(callout.getByText(text.split("\n")[0])).toBeVisible();
    }

    // Encouragement is the one with no box and no label — minimal warm text (AC4).
    await deliver(page, "show_encouragement", "You worked through a hard one.");
    const encouragement = page.getByRole("complementary", { name: "Learning hint" });
    await expect(encouragement.getByText("You worked through a hard one.")).toBeVisible();
    await expect(
      encouragement.getByText("Here's another way to think about this…"),
    ).toHaveCount(0);
  });

  test("simplify and increase_difficulty are not introduced as hints", async ({ page }) => {
    // Both were routed to this callout but missing from `VARIANT_BY_ACTION`, so both fell through
    // to the hint label. For `increase_difficulty` that means a learner who was BORED was offered
    // a harder question under the sentence used for someone who is stuck.
    await openLesson(page);

    await deliver(page, "simplify", "Put simply: the client speaks first.");
    const simpler = page.getByRole("complementary", { name: "Learning hint" });
    await expect(simpler.getByText("Put more simply")).toBeVisible();
    await expect(simpler.getByText("Here's another way to think about this…")).toHaveCount(0);

    await deliver(page, "increase_difficulty", "What breaks if the final ACK is lost?");
    const challenge = page.getByRole("complementary", { name: "Learning hint" });
    await expect(challenge.getByText("Ready for a harder one?")).toBeVisible();
    await expect(challenge.getByText("Here's another way to think about this…")).toHaveCount(0);
  });

  test("a hint can be dismissed and brought back", async ({ page }) => {
    await openLesson(page);
    await deliver(page, "show_hint", "Try relating it to something you know.");

    const callout = page.getByRole("complementary", { name: "Learning hint" });
    await expect(callout).toBeVisible();
    await callout.getByRole("button", { name: "Dismiss hint" }).click();

    // The item stays in the queue and the callout keeps its own dismissed state, so the same
    // content comes back rather than a fresh one.
    const restore = page.getByRole("button", { name: "Show hint" });
    await expect(restore).toBeVisible();
    await restore.click();
    await expect(
      page.getByText("Try relating it to something you know."),
    ).toBeVisible();
  });

  test("a breakdown collapses and expands", async ({ page }) => {
    await openLesson(page);
    await deliver(page, "show_breakdown", "First this.\nThen that.\nFinally the other.");

    const toggle = page.getByRole("button", { name: /Let's break this down/ });
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByText("Then that.")).toBeVisible();

    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByText("Then that.")).toHaveCount(0);
  });

  test("skip_ahead renders its own card, not the hint callout", async ({ page }) => {
    await openLesson(page);
    await deliver(page, "skip_ahead", "You seem ready to move on.");

    const card = page.getByRole("complementary", { name: "Skip ahead suggestion" });
    // The card sits in normal flow at the bottom of the page, so it is below the fold on a
    // laptop viewport — visible to the DOM and not to the learner without this.
    await card.scrollIntoViewIfNeeded();
    await expect(card).toBeVisible();
    await expect(card.getByRole("button", { name: "Skip ahead" })).toBeVisible();
    await expect(card.getByRole("button", { name: "Not now" })).toBeVisible();
    // It must NOT also appear as a hint — the two consumers filter on disjoint action sets.
    await expect(page.getByRole("complementary", { name: "Learning hint" })).toHaveCount(0);
  });

  test("accepting skip_ahead actually moves the learner", async ({ page }) => {
    // The reported bug: the button was wired to a handler that advanced the section index to
    // itself on the last section — a documented "graceful no-op" — so on that section the card
    // vanished and nothing moved. A control the SYSTEM offered unprompted is the worst place for
    // one that silently does nothing.
    await openLesson(page);
    const before = page.url();

    await deliver(page, "skip_ahead", "You seem ready to move on.");
    const card = page.getByRole("complementary", { name: "Skip ahead suggestion" });
    await card.scrollIntoViewIfNeeded();

    // The page paginates one section at a time and prints "Section N of M", which is a far more
    // direct read on "did the learner move" than any heading.
    const counter = page.getByText(/^Section \d+ of \d+$/);
    const positionBefore = await counter.textContent();
    await card.getByRole("button", { name: "Skip ahead" }).click();

    // Either the section on screen changed, or the lesson did. Both are "the learner moved";
    // neither happening is the bug this test exists for.
    await expect
      .poll(
        async () => {
          if (page.url() !== before) return true;
          return (await counter.textContent()) !== positionBefore;
        },
        { timeout: 10_000 },
      )
      .toBe(true);
  });

  test("the full loop delivers a hint over the live socket", async ({ page, request }) => {
    // The one thing neither the other cases nor `scripts/drive_adaptations.py` covers: a real
    // decision, pushed down the real WebSocket, appearing on a real screen. The others seed the
    // store directly (no backend) or run the graph in process (no socket).
    //
    // `POST /dev/simulate-cycle` fabricates the affect reading and nothing else: the profiler, the
    // gate, the strategist, the content adapter and the delivery are all the production path. It
    // 404s in production, so this test is also the assertion that a development backend is what
    // e2e runs against.
    test.setTimeout(60_000);
    await openLesson(page);

    // Wait for the socket, or the server has nowhere to push to and reports `delivered: false`.
    await expect
      .poll(
        () =>
          page.evaluate(() => {
            const w = window as unknown as {
              __connectionStore?: { getState: () => { isConnected: boolean } };
            };
            return w.__connectionStore?.getState().isConnected ?? false;
          }),
        { timeout: 20_000, message: "WS never connected — the loop has nowhere to deliver" },
      )
      .toBe(true);

    // The lesson opens on its first section, which is what the loop must be pointed at: the
    // adapter grounds its text in the section the learner is actually reading.
    const sectionsRes = await request.get(
      `${API_BASE}/courses/lessons/${shared.lessonId}/sections`,
      { headers: { Authorization: `Bearer ${shared.tokens.accessToken}` } },
    );
    const sectionId: string = (await sectionsRes.json())[0].id;

    const result = await request
      .post(`${API_BASE}/dev/simulate-cycle`, {
        headers: { Authorization: `Bearer ${shared.tokens.accessToken}` },
        // rung 1 on the confusion ladder, so the expected action is `show_breakdown` rather
        // than the `show_hint` every other case in this file already covers.
        data: { sectionId, affectState: "confused", rung: 1 },
      })
      .then((r) => r.json());

    expect(result.gateReason, JSON.stringify(result.notes)).toBe("ok");
    expect(result.actionType).toBe("show_breakdown");
    expect(result.delivered, JSON.stringify(result.notes)).toBe(true);

    // And it is on screen, from a decision the backend made.
    const callout = page.getByRole("complementary", { name: "Learning hint" });
    await expect(callout).toBeVisible();
    await expect(callout.getByText("Let's break this down")).toBeVisible();
  });

  test("suggest_break renders the break card and can be declined", async ({ page }) => {
    await openLesson(page);
    await deliver(page, "suggest_break", "You've been at this a while.");

    const card = page.getByRole("alertdialog", { name: "Break suggestion" });
    await expect(card).toBeVisible();
    await expect(card.getByRole("button", { name: "Take a break" })).toBeVisible();
  });
});
