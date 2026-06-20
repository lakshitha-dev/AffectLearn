import { describe, it, expect, beforeEach } from "vitest";
import { useAdaptationStore, type Adaptation } from "./adaptation-store";

function makeAdaptation(overrides: Partial<Adaptation> = {}): Adaptation {
  return {
    id: "a1",
    action: "show_hint",
    text: "Here's a hint.",
    variant: "show_hint",
    receivedAt: 1000,
    ...overrides,
  };
}

describe("useAdaptationStore", () => {
  beforeEach(() => {
    useAdaptationStore.getState().reset();
  });

  describe("initial state", () => {
    it("starts with an empty queue", () => {
      expect(useAdaptationStore.getState().adaptationQueue).toEqual([]);
    });
  });

  describe("pushAdaptation", () => {
    it("appends an adaptation to the queue", () => {
      useAdaptationStore.getState().pushAdaptation(makeAdaptation());
      const q = useAdaptationStore.getState().adaptationQueue;
      expect(q).toHaveLength(1);
      expect(q[0].action).toBe("show_hint");
      expect(q[0].id).toBe("a1");
    });

    it("preserves order across multiple pushes", () => {
      const s = useAdaptationStore.getState();
      s.pushAdaptation(makeAdaptation({ id: "a1" }));
      s.pushAdaptation(makeAdaptation({ id: "a2", action: "simplify" }));
      const q = useAdaptationStore.getState().adaptationQueue;
      expect(q.map((a) => a.id)).toEqual(["a1", "a2"]);
      expect(q[1].action).toBe("simplify");
    });
  });

  describe("dismissAdaptation", () => {
    it("removes the matching item by id", () => {
      const s = useAdaptationStore.getState();
      s.pushAdaptation(makeAdaptation({ id: "a1" }));
      s.pushAdaptation(makeAdaptation({ id: "a2" }));
      s.dismissAdaptation("a1");
      const q = useAdaptationStore.getState().adaptationQueue;
      expect(q.map((a) => a.id)).toEqual(["a2"]);
    });

    it("is a no-op for an unknown id", () => {
      const s = useAdaptationStore.getState();
      s.pushAdaptation(makeAdaptation({ id: "a1" }));
      s.dismissAdaptation("nope");
      expect(useAdaptationStore.getState().adaptationQueue).toHaveLength(1);
    });
  });

  describe("reset", () => {
    it("clears the queue", () => {
      const s = useAdaptationStore.getState();
      s.pushAdaptation(makeAdaptation({ id: "a1" }));
      s.pushAdaptation(makeAdaptation({ id: "a2" }));
      s.reset();
      expect(useAdaptationStore.getState().adaptationQueue).toEqual([]);
    });
  });

  describe("store shape", () => {
    it("exposes all expected fields and actions", () => {
      const state = useAdaptationStore.getState();
      expect(state).toHaveProperty("adaptationQueue");
      expect(Array.isArray(state.adaptationQueue)).toBe(true);
      expect(typeof state.pushAdaptation).toBe("function");
      expect(typeof state.dismissAdaptation).toBe("function");
      expect(typeof state.reset).toBe("function");
    });
  });
});
