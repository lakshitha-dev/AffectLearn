import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

// Mutable mock state so individual tests can flip webcam mode / connection.
const mocks = vi.hoisted(() => ({
  mode: { value: "adaptive" as "adaptive" | "behavioral" | "error" },
  isConnected: { value: true },
}));

vi.mock("@/stores/webcam-store", () => ({
  useWebcamStore: (selector: (s: { mode: string }) => unknown) =>
    selector({ mode: mocks.mode.value }),
}));

vi.mock("@/stores/connection-store", () => ({
  useConnectionStore: {
    getState: () => ({ isConnected: mocks.isConnected.value }),
  },
}));

import { useBehavioralSignals } from "./use-behavioral-signals";
import type { BehavioralWindowMessage } from "@/types/ws-messages";
import type { BehavioralEvent } from "@/types/behavioral-events";

const TRACKED_WINDOW_EVENTS = ["mousemove", "mousedown", "keydown", "scroll", "wheel"];

function lastWindowMessage(send: ReturnType<typeof vi.fn>): BehavioralWindowMessage {
  const calls = send.mock.calls;
  return calls[calls.length - 1][0] as BehavioralWindowMessage;
}

beforeEach(() => {
  vi.useFakeTimers();
  mocks.mode.value = "adaptive";
  mocks.isConnected.value = true;
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useBehavioralSignals", () => {
  it("is inert in error mode — no listeners, no sends (AC #1)", () => {
    mocks.mode.value = "error";
    const addSpy = vi.spyOn(window, "addEventListener");
    const send = vi.fn();

    const { unmount } = renderHook(() => useBehavioralSignals({ send }));

    const tracked = addSpy.mock.calls.filter((c) =>
      TRACKED_WINDOW_EVENTS.includes(c[0] as string),
    );
    expect(tracked.length).toBe(0);

    act(() => vi.advanceTimersByTime(60_000));
    expect(send).not.toHaveBeenCalled();
    unmount();
  });

  it("attaches all 6 listeners in adaptive mode (AC #1)", () => {
    const winAddSpy = vi.spyOn(window, "addEventListener");
    const docAddSpy = vi.spyOn(document, "addEventListener");
    const send = vi.fn();

    const { unmount } = renderHook(() => useBehavioralSignals({ send }));

    for (const ev of TRACKED_WINDOW_EVENTS) {
      expect(winAddSpy.mock.calls.some((c) => c[0] === ev)).toBe(true);
    }
    expect(
      docAddSpy.mock.calls.some((c) => c[0] === "visibilitychange"),
    ).toBe(true);
    unmount();
  });

  it("samples a continuously-moving cursor at 10 Hz — 10 samples in 1s (AC #2)", () => {
    const send = vi.fn();
    const { unmount } = renderHook(() =>
      useBehavioralSignals({ send, cycleMs: 1000, sampleMs: 100 }),
    );

    act(() => {
      // Move before every 100ms tick to emulate continuous movement — the H1 fix
      // only emits a sample when the cursor actually moved since the last tick.
      for (let i = 0; i < 10; i++) {
        window.dispatchEvent(
          new MouseEvent("mousemove", { clientX: i, clientY: i }),
        );
        vi.advanceTimersByTime(100);
      }
    });

    expect(send).toHaveBeenCalledTimes(1);
    const msg = lastWindowMessage(send);
    expect(msg.type).toBe("behavioral_window");
    expect(msg.data.summary.mouse_sample_count).toBe(10);
    const samples = msg.data.events.filter((e) => e.kind === "mouse_sample");
    expect(samples).toHaveLength(10);
    unmount();
  });

  it("stops sampling once the cursor is still — only moves are sampled (H1, AC #5)", () => {
    const send = vi.fn();
    const { unmount } = renderHook(() =>
      useBehavioralSignals({ send, cycleMs: 1000, sampleMs: 100 }),
    );

    act(() => {
      // One move, then a full second of stillness (10 aggregator ticks).
      window.dispatchEvent(
        new MouseEvent("mousemove", { clientX: 5, clientY: 5 }),
      );
      vi.advanceTimersByTime(1000);
    });

    const msg = lastWindowMessage(send);
    // Exactly one sample (the first tick after the single move); the remaining
    // ticks emit nothing because the cursor never moved again. Pre-H1 this would
    // have been ~10 constant-coordinate samples.
    expect(msg.data.summary.mouse_sample_count).toBe(1);
    expect(msg.data.summary.idle).toBe(false); // a sample exists, so not idle
    unmount();
  });

  it("sends a behavioral_window at the cycle boundary and clears the buffer (AC #4)", () => {
    const send = vi.fn();
    const { unmount } = renderHook(() =>
      useBehavioralSignals({ send, cycleMs: 1000, sampleMs: 100 }),
    );

    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));
      window.dispatchEvent(new MouseEvent("mousedown", { button: 0 }));
      vi.advanceTimersByTime(1000);
    });

    expect(send).toHaveBeenCalledTimes(1);
    const first = lastWindowMessage(send);
    expect(first.data.cycle_number).toBe(1);
    expect(first.data.summary.keystroke_count).toBe(1);
    expect(first.data.summary.mouse_click_count).toBe(1);
    expect(first.data.window_duration_ms).toBe(30_000);
    expect(first.data.sampling_rate_hz).toBe(10);
    expect(first.data.schema_version).toBe(2);

    // Next cycle with no input — buffer was cleared, cycle_number incremented.
    act(() => vi.advanceTimersByTime(1000));
    expect(send).toHaveBeenCalledTimes(2);
    const second = lastWindowMessage(send);
    expect(second.data.cycle_number).toBe(2);
    expect(second.data.summary.keystroke_count).toBe(0);
    expect(second.data.summary.mouse_click_count).toBe(0);
    unmount();
  });

  it("still sends an idle window with summary.idle === true (AC #5)", () => {
    const send = vi.fn();
    const { unmount } = renderHook(() =>
      useBehavioralSignals({ send, cycleMs: 1000, sampleMs: 100 }),
    );

    act(() => vi.advanceTimersByTime(1000));

    expect(send).toHaveBeenCalledTimes(1);
    const msg = lastWindowMessage(send);
    expect(msg.data.summary.idle).toBe(true);
    expect(msg.data.events).toEqual([]);
    expect(msg.data.summary.mouse_sample_count).toBe(0);
    unmount();
  });

  it("drops the cycle (no send) but clears the buffer when disconnected (AC #9)", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const send = vi.fn();
    mocks.isConnected.value = false;

    const { unmount } = renderHook(() =>
      useBehavioralSignals({ send, cycleMs: 1000, sampleMs: 100 }),
    );

    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "x" }));
      vi.advanceTimersByTime(1000);
    });

    expect(send).not.toHaveBeenCalled();
    expect(warnSpy).toHaveBeenCalledWith(
      "[useBehavioralSignals] cycle dropped — ws not connected",
      { cycle_number: 1 },
    );

    // Reconnect — the dropped window's events must NOT bleed into the next one.
    mocks.isConnected.value = true;
    act(() => vi.advanceTimersByTime(1000));
    expect(send).toHaveBeenCalledTimes(1);
    const msg = lastWindowMessage(send);
    expect(msg.data.cycle_number).toBe(2);
    expect(msg.data.summary.keystroke_count).toBe(0);
    unmount();
  });

  it("caps the buffer at 10000 and counts overflow as dropped_events (AC #9)", () => {
    const send = vi.fn();
    const { unmount } = renderHook(() =>
      useBehavioralSignals({ send, cycleMs: 1000, sampleMs: 100_000 }),
    );

    act(() => {
      for (let i = 0; i < 10_005; i++) {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));
      }
      vi.advanceTimersByTime(1000);
    });

    const msg = lastWindowMessage(send);
    expect(msg.data.events.length).toBe(10_000);
    expect(msg.data.dropped_events).toBe(5);
    unmount();
  });

  it("never serialises keystroke content — typing PASSWORD123 leaks nothing (AC #6)", () => {
    const send = vi.fn();
    const { unmount } = renderHook(() =>
      useBehavioralSignals({ send, cycleMs: 1000, sampleMs: 100_000 }),
    );

    act(() => {
      for (const ch of "PASSWORD123") {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: ch }));
      }
      vi.advanceTimersByTime(1000);
    });

    const msg = lastWindowMessage(send);
    const serialised = JSON.stringify(msg);

    // The typed UPPERCASE letters cannot appear in the all-lowercase wire schema —
    // if any did, content would be leaking. (Digits are NOT checked: numeric
    // fields like `ts` legitimately contain 1/2/3, which is unrelated to content.)
    for (const ch of "PASWORD") {
      expect(serialised).not.toContain(ch);
    }

    // Structural privacy guarantee: every key event carries ONLY category + timing,
    // never the raw character under any field name.
    const keyEvents = msg.data.events.filter((e) => e.kind === "key");
    expect(keyEvents).toHaveLength(11); // 8 letters + 3 digits, content discarded
    for (const e of keyEvents) {
      expect(Object.keys(e).sort()).toEqual([
        "category",
        "kind",
        "t_mono",
        "t_wall",
      ]);
    }
    unmount();
  });

  it("removes all 6 listeners and clears intervals on unmount (AC #1)", () => {
    const winRemoveSpy = vi.spyOn(window, "removeEventListener");
    const docRemoveSpy = vi.spyOn(document, "removeEventListener");
    const send = vi.fn();

    const { unmount } = renderHook(() =>
      useBehavioralSignals({ send, cycleMs: 1000, sampleMs: 100 }),
    );
    unmount();

    for (const ev of TRACKED_WINDOW_EVENTS) {
      expect(winRemoveSpy.mock.calls.some((c) => c[0] === ev)).toBe(true);
    }
    expect(
      docRemoveSpy.mock.calls.some((c) => c[0] === "visibilitychange"),
    ).toBe(true);

    // No timers should fire after unmount.
    act(() => vi.advanceTimersByTime(60_000));
    expect(send).not.toHaveBeenCalled();
  });

  it("records wheel scrolls and collapses the inertial scroll train (AC #7 / M3)", () => {
    let mono = 0;
    vi.spyOn(performance, "now").mockImplementation(() => mono);
    const setScrollY = (v: number) =>
      Object.defineProperty(window, "scrollY", { configurable: true, value: v });
    setScrollY(0);

    const send = vi.fn();
    const { unmount } = renderHook(() =>
      useBehavioralSignals({ send, cycleMs: 1000, sampleMs: 100_000 }),
    );

    act(() => {
      // Wheel gesture downward at t=100 — recorded with its deltaY.
      mono = 100;
      setScrollY(40);
      window.dispatchEvent(new WheelEvent("wheel", { deltaY: 120 }));
      // Two inertial scrolls within 50ms in the same direction — both collapsed.
      mono = 120;
      setScrollY(60);
      window.dispatchEvent(new Event("scroll"));
      mono = 150;
      setScrollY(80);
      window.dispatchEvent(new Event("scroll"));
      // A genuine scroll long after the gesture (>50ms gap) — recorded.
      mono = 400;
      setScrollY(120);
      window.dispatchEvent(new Event("scroll"));
      mono = 1000;
      vi.advanceTimersByTime(1000);
    });

    const msg = lastWindowMessage(send);
    const scrolls = msg.data.events.filter(
      (e): e is Extract<BehavioralEvent, { kind: "scroll" }> =>
        e.kind === "scroll",
    );
    // 1 wheel + 1 genuine late scroll; the inertial train was de-duped to nothing.
    expect(scrolls).toHaveLength(2);
    expect(msg.data.summary.scroll_event_count).toBe(2);
    expect(scrolls[0].delta_y).toBe(120);
    expect(scrolls[1].delta_y).toBe(0);
    unmount();
  });

  it("accumulates visibility_hidden_ms across hidden/visible transitions (AC #8)", () => {
    let mono = 0;
    vi.spyOn(performance, "now").mockImplementation(() => mono);
    const setVisibility = (state: "visible" | "hidden") =>
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        get: () => state,
      });
    setVisibility("visible");

    const send = vi.fn();
    const { unmount } = renderHook(() =>
      useBehavioralSignals({ send, cycleMs: 1000, sampleMs: 100_000 }),
    );

    act(() => {
      mono = 200;
      setVisibility("hidden");
      document.dispatchEvent(new Event("visibilitychange")); // hiddenSince = 200
      mono = 700;
      setVisibility("visible");
      document.dispatchEvent(new Event("visibilitychange")); // accum += 700 - 200
      mono = 1000;
      vi.advanceTimersByTime(1000);
    });

    const msg = lastWindowMessage(send);
    expect(msg.data.summary.visibility_hidden_ms).toBe(500);
    const visEvents = msg.data.events.filter((e) => e.kind === "visibility");
    expect(visEvents).toHaveLength(2);
    setVisibility("visible"); // restore for any later tests
    unmount();
  });

  it("does nothing when enabled is false", () => {
    const addSpy = vi.spyOn(window, "addEventListener");
    const send = vi.fn();
    const { unmount } = renderHook(() =>
      useBehavioralSignals({ send, enabled: false }),
    );
    const tracked = addSpy.mock.calls.filter((c) =>
      TRACKED_WINDOW_EVENTS.includes(c[0] as string),
    );
    expect(tracked.length).toBe(0);
    act(() => vi.advanceTimersByTime(60_000));
    expect(send).not.toHaveBeenCalled();
    unmount();
  });
});
