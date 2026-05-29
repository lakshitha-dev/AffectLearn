import { describe, it, expect, beforeEach } from "vitest";
import { useConnectionStore } from "./connection-store";

describe("useConnectionStore", () => {
  beforeEach(() => {
    useConnectionStore.getState().reset();
  });

  describe("initial state", () => {
    it("starts disconnected", () => {
      expect(useConnectionStore.getState().isConnected).toBe(false);
    });

    it("starts in 'idle' connection state", () => {
      expect(useConnectionStore.getState().connectionState).toBe("idle");
    });

    it("has no last error", () => {
      expect(useConnectionStore.getState().lastError).toBeNull();
    });

    it("has zero reconnect attempts", () => {
      expect(useConnectionStore.getState().reconnectAttempts).toBe(0);
    });

    it("has not restored a session", () => {
      expect(useConnectionStore.getState().sessionRestored).toBe(false);
    });
  });

  describe("setConnected", () => {
    it("flips isConnected to true", () => {
      useConnectionStore.getState().setConnected(true);
      expect(useConnectionStore.getState().isConnected).toBe(true);
    });

    it("flips isConnected back to false", () => {
      useConnectionStore.getState().setConnected(true);
      useConnectionStore.getState().setConnected(false);
      expect(useConnectionStore.getState().isConnected).toBe(false);
    });
  });

  describe("setConnectionState", () => {
    it.each([
      "idle",
      "connecting",
      "open",
      "reconnecting",
      "closed",
      "auth_failed",
    ] as const)("accepts state '%s'", (state) => {
      useConnectionStore.getState().setConnectionState(state);
      expect(useConnectionStore.getState().connectionState).toBe(state);
    });
  });

  describe("setError", () => {
    it("stores the message", () => {
      useConnectionStore.getState().setError("auth_failed");
      expect(useConnectionStore.getState().lastError).toBe("auth_failed");
    });

    it("clears the message when set to null", () => {
      useConnectionStore.getState().setError("something");
      useConnectionStore.getState().setError(null);
      expect(useConnectionStore.getState().lastError).toBeNull();
    });
  });

  describe("reconnect attempts", () => {
    it("incrementReconnect bumps the count", () => {
      useConnectionStore.getState().incrementReconnect();
      useConnectionStore.getState().incrementReconnect();
      useConnectionStore.getState().incrementReconnect();
      expect(useConnectionStore.getState().reconnectAttempts).toBe(3);
    });

    it("resetReconnect returns the count to zero", () => {
      useConnectionStore.getState().incrementReconnect();
      useConnectionStore.getState().incrementReconnect();
      useConnectionStore.getState().resetReconnect();
      expect(useConnectionStore.getState().reconnectAttempts).toBe(0);
    });
  });

  describe("markSessionRestored", () => {
    it("flips sessionRestored to true", () => {
      useConnectionStore.getState().markSessionRestored();
      expect(useConnectionStore.getState().sessionRestored).toBe(true);
    });
  });

  describe("reset", () => {
    it("returns every field to its initial value", () => {
      const s = useConnectionStore.getState();
      s.setConnected(true);
      s.setConnectionState("open");
      s.setError("boom");
      s.incrementReconnect();
      s.markSessionRestored();

      s.reset();

      const after = useConnectionStore.getState();
      expect(after.isConnected).toBe(false);
      expect(after.connectionState).toBe("idle");
      expect(after.lastError).toBeNull();
      expect(after.reconnectAttempts).toBe(0);
      expect(after.sessionRestored).toBe(false);
    });
  });

  describe("store shape", () => {
    it("exposes all expected fields and actions", () => {
      const state = useConnectionStore.getState();
      expect(state).toHaveProperty("isConnected");
      expect(state).toHaveProperty("connectionState");
      expect(state).toHaveProperty("lastError");
      expect(state).toHaveProperty("reconnectAttempts");
      expect(state).toHaveProperty("sessionRestored");
      expect(typeof state.setConnected).toBe("function");
      expect(typeof state.setConnectionState).toBe("function");
      expect(typeof state.setError).toBe("function");
      expect(typeof state.incrementReconnect).toBe("function");
      expect(typeof state.resetReconnect).toBe("function");
      expect(typeof state.markSessionRestored).toBe("function");
      expect(typeof state.reset).toBe("function");
    });
  });
});
