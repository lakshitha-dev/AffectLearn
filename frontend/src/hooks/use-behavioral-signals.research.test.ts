import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

// Schema v2: research context recorded alongside the model's input without changing it.

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

function windows(send: ReturnType<typeof vi.fn>): BehavioralWindowMessage[] {
  return send.mock.calls.map((c) => c[0] as BehavioralWindowMessage);
}

function mount(html: string): HTMLElement {
  const host = document.createElement("div");
  host.innerHTML = html;
  document.body.appendChild(host);
  return host;
}

beforeEach(() => {
  vi.useFakeTimers();
  mocks.mode.value = "adaptive";
  mocks.isConnected.value = true;
  document.body.innerHTML = "";
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useBehavioralSignals research context (schema v2)", () => {
  it("names the tracked element a click landed on, never its text", () => {
    const host = mount('<button data-track="nav-next"><span>Secret label</span></button>');
    const send = vi.fn();
    const { unmount } = renderHook(() => useBehavioralSignals({ send }));

    act(() => {
      host.querySelector("span")!.dispatchEvent(
        new MouseEvent("mousedown", { bubbles: true, clientX: 5, clientY: 6 }),
      );
      vi.advanceTimersByTime(30_000);
    });

    const click = windows(send)[0].data.events.find((e) => e.kind === "mouse_click");
    expect(click).toMatchObject({ kind: "mouse_click", target: "nav-next", x: 5, y: 6 });
    expect(JSON.stringify(windows(send)[0])).not.toContain("Secret label");
    unmount();
  });

  it("records nothing at all from a password field or a data-private element", () => {
    const host = mount(
      '<input type="password" id="pw" /><div data-private><input id="priv" /></div>',
    );
    const send = vi.fn();
    const { unmount } = renderHook(() => useBehavioralSignals({ send }));

    act(() => {
      for (const id of ["pw", "priv"]) {
        const el = host.querySelector(`#${id}`)!;
        el.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "a" }));
        el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
        el.dispatchEvent(new Event("paste", { bubbles: true }));
      }
      vi.advanceTimersByTime(30_000);
    });

    const data = windows(send)[0].data;
    expect(data.events.filter((e) => e.kind === "key" || e.kind === "mouse_click")).toEqual([]);
    expect(data.ui_events).toEqual([]);
    unmount();
  });

  it("records hover dwell on tracked elements in ui_events, outside the model's events", () => {
    const host = mount('<div data-track="block-1">text</div><div id="plain">plain</div>');
    const send = vi.fn();
    const { unmount } = renderHook(() => useBehavioralSignals({ send }));

    act(() => {
      host.querySelector('[data-track="block-1"]')!.dispatchEvent(
        new MouseEvent("mouseover", { bubbles: true }),
      );
      vi.advanceTimersByTime(2_000);
      host.querySelector("#plain")!.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
      vi.advanceTimersByTime(28_000);
    });

    const data = windows(send)[0].data;
    expect(data.ui_events).toEqual([
      expect.objectContaining({ kind: "hover", target: "block-1", dwell_ms: 2_000 }),
    ]);
    expect(data.events.some((e) => (e.kind as string) === "hover")).toBe(false);
    unmount();
  });

  it("splits a hover that spans a window boundary between the two windows", () => {
    const host = mount('<div data-track="block-2">text</div>');
    const send = vi.fn();
    const { unmount } = renderHook(() => useBehavioralSignals({ send }));

    act(() => {
      vi.advanceTimersByTime(20_000);
      host.firstElementChild!.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
      vi.advanceTimersByTime(20_000); // boundary at 30 s, then 10 s more
      host.firstElementChild!.dispatchEvent(
        new MouseEvent("mouseover", { bubbles: true, relatedTarget: null }),
      );
      document.body.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
      vi.advanceTimersByTime(20_000);
    });

    const [first, second] = windows(send).map((w) => w.data.ui_events ?? []);
    expect(first).toEqual([expect.objectContaining({ target: "block-2", dwell_ms: 10_000 })]);
    expect(second).toEqual([expect.objectContaining({ target: "block-2", dwell_ms: 10_000 })]);
    unmount();
  });

  it("records a clipboard action and where it happened, never the content", () => {
    const host = mount('<textarea data-track="exercise-3-editor"></textarea>');
    const send = vi.fn();
    const { unmount } = renderHook(() => useBehavioralSignals({ send }));

    act(() => {
      host.firstElementChild!.dispatchEvent(new Event("paste", { bubbles: true }));
      vi.advanceTimersByTime(30_000);
    });

    expect(windows(send)[0].data.ui_events).toEqual([
      expect.objectContaining({ kind: "clipboard", action: "paste", target: "exercise-3-editor" }),
    ]);
    unmount();
  });

  it("carries the viewport and one page_instance_id across the windows of a mount", () => {
    const send = vi.fn();
    const { unmount } = renderHook(() => useBehavioralSignals({ send }));
    act(() => vi.advanceTimersByTime(60_000));

    const [a, b] = windows(send);
    expect(a.data.schema_version).toBe(2);
    expect(a.data.viewport).toEqual(
      expect.objectContaining({ w: window.innerWidth, h: window.innerHeight }),
    );
    expect(a.data.page_instance_id).toBeTruthy();
    expect(b.data.page_instance_id).toBe(a.data.page_instance_id);
    unmount();
  });

  it("gives a fresh page_instance_id to a new mount", () => {
    const send = vi.fn();
    const first = renderHook(() => useBehavioralSignals({ send }));
    act(() => vi.advanceTimersByTime(30_000));
    first.unmount();
    const second = renderHook(() => useBehavioralSignals({ send }));
    act(() => vi.advanceTimersByTime(30_000));
    second.unmount();

    const [a, b] = windows(send);
    expect(a.data.page_instance_id).not.toBe(b.data.page_instance_id);
  });
});
