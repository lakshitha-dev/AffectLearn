"use client";

/**
 * useBehavioralSignals — mouse/keyboard/scroll signal capture at 10 Hz, batched
 * into 30-second windows and shipped over the WebSocket from Story 4.1.
 *
 * Privacy contract:
 *   - Captures event TIMING and CATEGORY only.
 *   - The actual character typed is NEVER read into a variable that outlives the
 *     event handler frame. `event.key` is consumed by `categoriseKey(...)` and
 *     discarded. There is no toggle to expose content elsewhere.
 *
 * Train/serve consistency:
 *   - This hook ships RAW timed events. Backend (Story 4.4b) extracts the Bi-LSTM
 *     features. See `ml-training-guide-behavioral.md` §6-7 for the feature list
 *     and the train/serve consistency argument.
 *
 * Dependencies (Story 4.1): the lesson page mounts `useWebSocket()` once and
 * passes its `send` function to this hook via `options.send`. We do NOT call
 * `useWebSocket()` here — the architecture mandates a single connection per
 * learner session. `isConnected` is read non-reactively from the connection
 * store at the cycle boundary (AC #9).
 */

import { useEffect, useRef } from "react";

import { useConnectionStore } from "@/stores/connection-store";
import { useWebcamStore } from "@/stores/webcam-store";
import { categoriseKey } from "@/lib/key-category";
import {
  assertNever,
  type BehavioralDebug,
  type BehavioralEvent,
  type BehavioralWindowSummary,
} from "@/types/behavioral-events";
import type {
  BehavioralWindowMessage,
  WSMessage,
} from "@/types/ws-messages";

// --- Locked constants (see story Dev Notes "Sampling Rate, Window Length") ---
const SAMPLE_INTERVAL_MS = 100; // 10 Hz aggregator cadence (AC #2)
const SAMPLING_RATE_HZ = 10;
const DEFAULT_CYCLE_MS = 30_000; // 30s window boundary (AC #4)
const WINDOW_DURATION_MS = 30_000;
const SCHEMA_VERSION = 1;
const BUFFER_CAP = 10_000; // hard per-cycle cap (AC #9)
const WHEEL_SCROLL_DEDUPE_MS = 50; // wheel→scroll de-dupe window (AC #7)

const IS_DEV =
  typeof process !== "undefined" && process.env.NODE_ENV !== "production";

export interface UseBehavioralSignalsOptions {
  /** Send function from the parent's `useWebSocket()` call (Story 4.1). */
  send?: (msg: WSMessage) => void;
  /** Force-disable even in a non-error webcam mode (e.g. test harness). */
  enabled?: boolean;
  /** Override the 100ms aggregator interval (testing only). */
  sampleMs?: number;
  /** Override the 30000ms cycle interval (testing only). */
  cycleMs?: number;
  /**
   * The section the learner is currently on. Sent with each window so the server can ground
   * adaptation prompts in the material on screen. Read through a ref internally so that
   * navigating between sections does not restart the aggregator.
   */
  sectionId?: string;
}

export interface UseBehavioralSignalsReturn {
  /** Live debug ref — populated only in dev (AC #10); null in production. */
  debug: React.RefObject<BehavioralDebug | null>;
  /**
   * The cycle currently being accumulated.
   *
   * Exposed so learner-response events (`self_report`, `adaptation_interaction`) can name the
   * detection cycle they happened during. Without it every such event landed with
   * `cycle_number: 0`, and a learner's answer to a hint could not be aligned to the cycle whose
   * detection produced it — which is the join the post-intervention window is built on.
   *
   * A REF rather than state, deliberately: this advances every 30s and nothing renders from it,
   * so returning state would re-render the whole lesson page on each cycle boundary for nothing.
   * Read it at send time.
   */
  cycleNumber: React.RefObject<number>;
}

function makeEmptyDebug(): BehavioralDebug {
  return {
    eventsPerSecond: 0,
    aggregatorTickCount: 0,
    aggregatorMissedTicks: 0,
    lastCycleDroppedEvents: 0,
    lastCycleMessageBytes: 0,
  };
}

interface MousePos {
  x: number;
  y: number;
  t_mono: number;
  t_wall: number;
}

export function useBehavioralSignals(
  options: UseBehavioralSignalsOptions = {},
): UseBehavioralSignalsReturn {
  const { send, enabled = true, sampleMs, cycleMs, sectionId } = options;
  const mode = useWebcamStore((s) => s.mode);

  // Ref rather than a dependency — see the matching note in `use-media-pipe.ts`. The learner
  // changes section far more often than the 30s window, and restarting the aggregator would
  // discard the partially-collected window.
  const sectionIdRef = useRef<string | undefined>(sectionId);
  sectionIdRef.current = sectionId;
  // The section this 30 s window STARTED on. A window is sent when it closes, so labelling it with
  // the section on screen at send time made "bored for 25 s on page A" arrive as a reading about
  // page B, and the hint was written for the wrong page. The server withholds a reading whose
  // section is no longer on screen.
  const windowSectionRef = useRef<string | undefined>(sectionId);

  const debugRef = useRef<BehavioralDebug | null>(
    IS_DEV ? makeEmptyDebug() : null,
  );

  // Stable ref to `send` so the effect doesn't re-fire when the caller passes a
  // new function reference (Story 4.2 confirmed `send` is stable, but guard anyway).
  const sendRef = useRef(send);
  sendRef.current = send;

  // H2: cycle numbering lives at hook scope so it persists across effect re-runs
  // (e.g. a webcam-mode flip adaptive→behavioral mid-lesson). It resets to 1 only
  // when the component itself remounts — i.e. on lesson navigation (AC #11) — so
  // the backend never sees a duplicate `cycle_number: 1` within one session.
  const cycleNumberRef = useRef(1);

  // M1: monotonic baseline captured once per component mount, so `t_mono` is truly
  // "milliseconds since hook mount" (AC #3 / behavioral-events.ts), not raw
  // performance.now() (which is relative to page navigation start).
  const mountMonoRef = useRef<number | null>(null);
  if (
    mountMonoRef.current === null &&
    typeof performance !== "undefined"
  ) {
    mountMonoRef.current = performance.now();
  }

  useEffect(() => {
    if (!enabled) return;
    if (mode === "error") return; // AC #1: inert during the 5s error→behavioral transition
    if (typeof window === "undefined") return; // SSR safety

    const mountMono = mountMonoRef.current ?? performance.now();
    /** Monotonic clock, milliseconds since hook mount (M1). */
    const monoNow = (): number => performance.now() - mountMono;

    // --- Per-activation state (closed over by the handlers) ---
    let buffer: BehavioralEvent[] = [];
    let dropped = 0;
    let lastMousePos: MousePos | null = null;
    // H1: only emit a mouse_sample when the cursor actually moved since the last
    // aggregator tick. A motionless window therefore produces mouse_samples: [].
    let mouseMovedSinceTick = false;
    let lastScrollY = typeof window !== "undefined" ? window.scrollY : 0;
    let lastWheelTimeMono: number | null = null;
    let lastWheelDirection: "up" | "down" | "none" | null = null;

    let cycleStartMono = monoNow();
    let cycleStartWall = Date.now();

    // Visibility-hidden accounting (AC #8).
    let visibilityHiddenAccumMs = 0;
    let hiddenSinceMono: number | null =
      typeof document !== "undefined" && document.visibilityState === "hidden"
        ? cycleStartMono
        : null;

    // Debug-only counters (AC #10).
    let aggregatorTickCount = 0;
    let eventsThisCycle = 0;

    if (IS_DEV) debugRef.current = makeEmptyDebug();

    /** Bounded push — drops + counts beyond the AC #9 cap. */
    function pushEvent(e: BehavioralEvent): void {
      if (buffer.length >= BUFFER_CAP) {
        dropped += 1;
        return;
      }
      buffer.push(e);
      if (IS_DEV) eventsThisCycle += 1;
    }

    // --- Listener handlers ---
    function handleMouseMove(e: MouseEvent): void {
      // AC #2: store only the MOST RECENT position; the aggregator samples it.
      lastMousePos = {
        x: e.clientX,
        y: e.clientY,
        t_mono: monoNow(),
        t_wall: Date.now(),
      };
      mouseMovedSinceTick = true; // H1
    }

    function handleMouseDown(e: MouseEvent): void {
      const button = (e.button === 0 || e.button === 1 || e.button === 2
        ? e.button
        : 0) as 0 | 1 | 2;
      pushEvent({
        kind: "mouse_click",
        x: e.clientX,
        y: e.clientY,
        button,
        t_mono: monoNow(),
        t_wall: Date.now(),
      });
    }

    function handleKeyDown(e: KeyboardEvent): void {
      // PRIVACY: categoriseKey consumes e.key and discards it. The raw character
      // is never stored on the event object we buffer.
      pushEvent({
        kind: "key",
        category: categoriseKey(e.key),
        t_mono: monoNow(),
        t_wall: Date.now(),
      });
    }

    function handleScroll(): void {
      const scrollY = window.scrollY;
      const direction: "up" | "down" | "none" =
        scrollY > lastScrollY ? "down" : scrollY < lastScrollY ? "up" : "none";
      lastScrollY = scrollY;

      // AC #7 / M3 de-dupe: a `wheel` always precedes the resulting `scroll`, and a
      // single inertial gesture fires MANY scroll events. Suppress native scrolls
      // that follow a wheel (or a previously-suppressed scroll) within 50ms in the
      // same direction, refreshing the deadline each time so the whole inertial
      // train collapses — not just the first event. Genuine keyboard/scrollbar
      // scrolls (no preceding wheel within the window) are still recorded.
      const now = monoNow();
      if (
        lastWheelTimeMono !== null &&
        now - lastWheelTimeMono < WHEEL_SCROLL_DEDUPE_MS &&
        direction === lastWheelDirection
      ) {
        lastWheelTimeMono = now; // M3: extend the dedupe window across the train
        return;
      }

      pushEvent({
        kind: "scroll",
        scroll_y: scrollY,
        delta_y: 0,
        direction,
        t_mono: now,
        t_wall: Date.now(),
      });
    }

    function handleWheel(e: WheelEvent): void {
      const now = monoNow();
      const direction: "up" | "down" | "none" =
        e.deltaY > 0 ? "down" : e.deltaY < 0 ? "up" : "none";
      lastWheelTimeMono = now;
      lastWheelDirection = direction;
      pushEvent({
        kind: "scroll",
        scroll_y: window.scrollY,
        delta_y: e.deltaY,
        direction,
        t_mono: now,
        t_wall: Date.now(),
      });
    }

    /**
     * Record a visibility/attention transition.
     *
     * `visibilitychange` only fires for TAB switches and minimising — it does NOT fire when the
     * learner switches to another application with this tab still frontmost, which is exactly
     * the "went to look something up" case that matters most for disengagement. `blur`/`focus`
     * cover that, so both feed the same accounting.
     *
     * Transitions are de-duplicated: the two event sources overlap (switching tabs fires both
     * `visibilitychange` and `blur`), and double-counting would inflate `tab_switch_count` and
     * corrupt the hidden-time integral.
     */
    function setAttentionState(hidden: boolean): void {
      const now = monoNow();
      if (hidden === (hiddenSinceMono !== null)) return; // no change — ignore the duplicate
      if (hidden) {
        hiddenSinceMono = now;
      } else if (hiddenSinceMono !== null) {
        visibilityHiddenAccumMs += now - hiddenSinceMono;
        hiddenSinceMono = null;
      }
      pushEvent({
        kind: "visibility",
        state: hidden ? "hidden" : "visible",
        t_mono: now,
        t_wall: Date.now(),
      });
    }

    function handleVisibility(): void {
      setAttentionState(document.visibilityState === "hidden");
    }

    function handleBlur(): void {
      setAttentionState(true);
    }

    function handleFocus(): void {
      // Only "visible" if the tab is also foregrounded — a focus event while the tab is hidden
      // should not clear the hidden state.
      setAttentionState(document.visibilityState === "hidden");
    }

    // --- 10 Hz aggregator (AC #2) ---
    function aggregatorTick(): void {
      if (IS_DEV) aggregatorTickCount += 1;
      // H1: emit a sample only when the cursor moved since the last tick. This
      // covers the cursor-never-entered case (lastMousePos null) too, and lets a
      // motionless "reading" window report mouse_samples: [] / summary.idle: true
      // (Success Criteria line 44, AC #5).
      if (lastMousePos === null || !mouseMovedSinceTick) {
        if (IS_DEV) updateLiveDebug();
        return;
      }
      pushEvent({
        kind: "mouse_sample",
        x: lastMousePos.x,
        y: lastMousePos.y,
        t_mono: monoNow(), // honest cadence timestamp
        t_wall: Date.now(),
      });
      mouseMovedSinceTick = false; // H1: consumed — wait for the next real move
      if (IS_DEV) updateLiveDebug();
    }

    function updateLiveDebug(): void {
      if (!debugRef.current) return;
      const elapsedSec = Math.max(0.001, (monoNow() - cycleStartMono) / 1000);
      debugRef.current.eventsPerSecond = eventsThisCycle / elapsedSec;
      debugRef.current.aggregatorTickCount = aggregatorTickCount;
    }

    // --- 30s cycle boundary (AC #4, #5, #9) ---
    function cycleHandler(): void {
      const endMono = monoNow();
      const endWall = Date.now();

      // Finalise visibility-hidden time for this window (AC #8).
      let hiddenMs = visibilityHiddenAccumMs;
      if (hiddenSinceMono !== null) {
        hiddenMs += endMono - hiddenSinceMono;
        // Carry the "still hidden" baseline into the next window.
        hiddenSinceMono = endMono;
      }
      hiddenMs = Math.min(WINDOW_DURATION_MS, Math.max(0, hiddenMs));

      const summary = summarise(buffer, hiddenMs);
      const cycleNumber = cycleNumberRef.current;

      const message: BehavioralWindowMessage = {
        type: "behavioral_window",
        ts: endWall,
        data: {
          cycle_number: cycleNumber,
          capture_started_at_mono: cycleStartMono,
          capture_ended_at_mono: endMono,
          capture_started_at_wall: cycleStartWall,
          capture_ended_at_wall: endWall,
          window_duration_ms: WINDOW_DURATION_MS,
          sampling_rate_hz: SAMPLING_RATE_HZ,
          schema_version: SCHEMA_VERSION,
          events: buffer,
          summary,
          dropped_events: dropped,
          section_id: windowSectionRef.current ?? sectionIdRef.current,
        },
      };
      // The next window starts now, on whatever section is on screen now.
      windowSectionRef.current = sectionIdRef.current;

      // AC #9: drop (do NOT queue) when the socket is down — stale 30s windows
      // would corrupt downstream temporal modelling.
      if (!useConnectionStore.getState().isConnected) {
        console.warn(
          "[useBehavioralSignals] cycle dropped — ws not connected",
          { cycle_number: cycleNumber },
        );
      } else if (sendRef.current) {
        sendRef.current(message);
      } else {
        console.warn(
          "[useBehavioralSignals] cycle dropped — no send function provided",
          { cycle_number: cycleNumber },
        );
      }

      if (IS_DEV && debugRef.current) {
        const expectedTicks = Math.floor(
          (endMono - cycleStartMono) / SAMPLE_INTERVAL_MS,
        );
        debugRef.current.aggregatorMissedTicks = Math.max(
          0,
          expectedTicks - aggregatorTickCount,
        );
        debugRef.current.lastCycleDroppedEvents = dropped;
        debugRef.current.lastCycleMessageBytes = JSON.stringify(
          message.data,
        ).length;
      }

      // Reset for the next window. `cycleNumberRef` increments (never resets here);
      // it only returns to 1 when the component remounts (AC #11 / H2).
      cycleNumberRef.current += 1;
      buffer = [];
      dropped = 0;
      visibilityHiddenAccumMs = 0;
      cycleStartMono = endMono;
      cycleStartWall = endWall;
      aggregatorTickCount = 0;
      eventsThisCycle = 0;
    }

    // --- Attach listeners + intervals (AC #1) ---
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mousedown", handleMouseDown);
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("scroll", handleScroll, { passive: true });
    window.addEventListener("wheel", handleWheel, { passive: true });
    document.addEventListener("visibilitychange", handleVisibility);
    // Catches switching to another APPLICATION, which visibilitychange does not fire for.
    window.addEventListener("blur", handleBlur);
    window.addEventListener("focus", handleFocus);

    const aggregatorId = setInterval(
      aggregatorTick,
      sampleMs ?? SAMPLE_INTERVAL_MS,
    );
    const cycleId = setInterval(cycleHandler, cycleMs ?? DEFAULT_CYCLE_MS);

    // --- Cleanup (AC #1): idempotent for React 19 StrictMode double-mount ---
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mousedown", handleMouseDown);
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("scroll", handleScroll);
      window.removeEventListener("wheel", handleWheel);
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("blur", handleBlur);
      window.removeEventListener("focus", handleFocus);
      clearInterval(aggregatorId);
      clearInterval(cycleId);
      buffer = [];
      lastMousePos = null;
    };
  }, [enabled, mode, sampleMs, cycleMs]);

  return { debug: debugRef, cycleNumber: cycleNumberRef };
}

/** Single-pass summary of a window's buffer (AC #4). */
function summarise(
  events: BehavioralEvent[],
  visibilityHiddenMs: number,
): BehavioralWindowSummary {
  let mouseSampleCount = 0;
  let mouseClickCount = 0;
  let keystrokeCount = 0;
  let backspaceCount = 0;
  let scrollEventCount = 0;

  for (const e of events) {
    switch (e.kind) {
      case "mouse_sample":
        mouseSampleCount += 1;
        break;
      case "mouse_click":
        mouseClickCount += 1;
        break;
      case "key":
        keystrokeCount += 1;
        if (e.category === "backspace") backspaceCount += 1;
        break;
      case "scroll":
        scrollEventCount += 1;
        break;
      case "visibility":
        break;
      default:
        assertNever(e);
    }
  }

  return {
    mouse_sample_count: mouseSampleCount,
    mouse_click_count: mouseClickCount,
    keystroke_count: keystrokeCount,
    backspace_count: backspaceCount,
    scroll_event_count: scrollEventCount,
    visibility_hidden_ms: visibilityHiddenMs,
    // AC #4 formula (authoritative field definition). With the H1 sampling fix, a
    // motionless window has mouse_sample_count === 0, so `idle` is now reachable
    // for a genuine "reading without input" window — matching Success Criteria.
    idle:
      mouseSampleCount === 0 && keystrokeCount === 0 && scrollEventCount === 0,
  };
}
