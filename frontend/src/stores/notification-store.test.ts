import { describe, it, expect, beforeEach } from "vitest";
import {
  useNotificationStore,
  MAX_VISIBLE,
  QUEUE_DELAY_MS,
  type ToastSpec,
} from "./notification-store";

function makeSpec(overrides: Partial<ToastSpec> = {}): ToastSpec {
  return {
    id: "t1",
    level: "info",
    message: "Hello.",
    ...overrides,
  };
}

describe("useNotificationStore", () => {
  beforeEach(() => {
    useNotificationStore.getState().reset();
  });

  describe("constants", () => {
    it("caps visible toasts at 2 and spaces releases by 500ms", () => {
      expect(MAX_VISIBLE).toBe(2);
      expect(QUEUE_DELAY_MS).toBe(500);
    });
  });

  describe("initial state", () => {
    it("starts with an empty queue and zero visible", () => {
      const s = useNotificationStore.getState();
      expect(s.queue).toEqual([]);
      expect(s.visibleCount).toBe(0);
    });
  });

  describe("enqueue", () => {
    it("appends a spec to the queue", () => {
      useNotificationStore.getState().enqueue(makeSpec());
      const q = useNotificationStore.getState().queue;
      expect(q).toHaveLength(1);
      expect(q[0].id).toBe("t1");
      expect(q[0].level).toBe("info");
    });

    it("preserves FIFO order across multiple enqueues", () => {
      const s = useNotificationStore.getState();
      s.enqueue(makeSpec({ id: "t1" }));
      s.enqueue(makeSpec({ id: "t2", level: "error" }));
      const q = useNotificationStore.getState().queue;
      expect(q.map((x) => x.id)).toEqual(["t1", "t2"]);
      expect(q[1].level).toBe("error");
    });
  });

  describe("onToastClosed", () => {
    it("decrements visibleCount", () => {
      useNotificationStore.getState().setVisibleCount(2);
      useNotificationStore.getState().onToastClosed();
      expect(useNotificationStore.getState().visibleCount).toBe(1);
    });

    it("floors visibleCount at 0", () => {
      useNotificationStore.getState().onToastClosed();
      expect(useNotificationStore.getState().visibleCount).toBe(0);
    });
  });

  describe("setVisibleCount / setQueue", () => {
    it("sets the visible count (floored at 0)", () => {
      useNotificationStore.getState().setVisibleCount(3);
      expect(useNotificationStore.getState().visibleCount).toBe(3);
      useNotificationStore.getState().setVisibleCount(-5);
      expect(useNotificationStore.getState().visibleCount).toBe(0);
    });

    it("replaces the queue", () => {
      const s = useNotificationStore.getState();
      s.enqueue(makeSpec({ id: "t1" }));
      s.setQueue([makeSpec({ id: "t2" })]);
      expect(useNotificationStore.getState().queue.map((x) => x.id)).toEqual([
        "t2",
      ]);
    });
  });

  describe("reset", () => {
    it("clears the queue and visible count", () => {
      const s = useNotificationStore.getState();
      s.enqueue(makeSpec({ id: "t1" }));
      s.setVisibleCount(2);
      s.reset();
      const after = useNotificationStore.getState();
      expect(after.queue).toEqual([]);
      expect(after.visibleCount).toBe(0);
    });
  });

  describe("store shape", () => {
    it("exposes all expected fields and actions", () => {
      const state = useNotificationStore.getState();
      expect(state).toHaveProperty("visibleCount");
      expect(state).toHaveProperty("queue");
      expect(Array.isArray(state.queue)).toBe(true);
      expect(typeof state.enqueue).toBe("function");
      expect(typeof state.onToastClosed).toBe("function");
      expect(typeof state.setVisibleCount).toBe("function");
      expect(typeof state.setQueue).toBe("function");
      expect(typeof state.reset).toBe("function");
    });
  });
});
