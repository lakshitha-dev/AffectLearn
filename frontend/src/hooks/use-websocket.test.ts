import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

// vi.mock is hoisted — use vi.hoisted so the spies/class are available at hoist time.
const mocks = vi.hoisted(() => {
  const sendSpy = vi.fn();
  const closeSpy = vi.fn();

  interface MockListenerMap {
    open: Array<(e: { type: "open" }) => void>;
    message: Array<(e: { type: "message"; data: string }) => void>;
    close: Array<(e: { type: "close"; code: number; reason: string }) => void>;
    error: Array<(e: { type: "error" }) => void>;
  }

  class MockReconnectingWebSocket {
    static readonly OPEN = 1;
    static instance: MockReconnectingWebSocket | null = null;

    readyState = 1;
    listeners: MockListenerMap = { open: [], message: [], close: [], error: [] };

    constructor() {
      MockReconnectingWebSocket.instance = this;
    }

    addEventListener<K extends keyof MockListenerMap>(
      type: K,
      listener: MockListenerMap[K][number],
    ): void {
      this.listeners[type].push(listener as never);
    }

    removeEventListener<K extends keyof MockListenerMap>(
      type: K,
      listener: MockListenerMap[K][number],
    ): void {
      this.listeners[type] = this.listeners[type].filter(
        (l) => l !== listener,
      ) as MockListenerMap[K];
    }

    send(payload: string): void {
      sendSpy(payload);
    }

    close(): void {
      closeSpy();
    }

    emitOpen() {
      this.listeners.open.forEach((l) => l({ type: "open" }));
    }
    emitMessage(data: string) {
      this.listeners.message.forEach((l) => l({ type: "message", data }));
    }
    emitClose(code: number, reason = "") {
      this.listeners.close.forEach((l) => l({ type: "close", code, reason }));
    }
  }

  const toastErrorSpy = vi.fn();
  const toastSuccessSpy = vi.fn();

  return {
    MockReconnectingWebSocket,
    sendSpy,
    closeSpy,
    toastErrorSpy,
    toastSuccessSpy,
  };
});

vi.mock("reconnecting-websocket", () => ({
  default: mocks.MockReconnectingWebSocket,
}));

vi.mock("sonner", () => ({
  toast: { error: mocks.toastErrorSpy, success: mocks.toastSuccessSpy },
}));

const routerPushSpy = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPushSpy }),
}));

import { useWebSocket } from "./use-websocket";
import { useConnectionStore } from "@/stores/connection-store";
import { useSessionStore } from "@/stores/session-store";

const VALID_FUTURE_TS = Date.now() + 60_000;

function authenticate() {
  useSessionStore.setState({
    accessToken: "tok-123",
    refreshToken: "ref-123",
    expiresAt: VALID_FUTURE_TS,
    user: null,
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  mocks.sendSpy.mockReset();
  mocks.closeSpy.mockReset();
  mocks.toastErrorSpy.mockReset();
  mocks.toastSuccessSpy.mockReset();
  mocks.MockReconnectingWebSocket.instance = null;
  routerPushSpy.mockReset();
  useConnectionStore.getState().reset();
});

afterEach(() => {
  vi.useRealTimers();
  useSessionStore.setState({
    accessToken: null,
    refreshToken: null,
    expiresAt: null,
    user: null,
  });
});

describe("useWebSocket", () => {
  it("does not open a connection when unauthenticated", () => {
    const { unmount } = renderHook(() => useWebSocket());
    expect(mocks.MockReconnectingWebSocket.instance).toBeNull();
    unmount();
  });

  it("opens a connection and flips isConnected on open", () => {
    authenticate();
    const { unmount } = renderHook(() => useWebSocket());

    expect(mocks.MockReconnectingWebSocket.instance).not.toBeNull();
    act(() => {
      mocks.MockReconnectingWebSocket.instance!.emitOpen();
    });

    expect(useConnectionStore.getState().isConnected).toBe(true);
    expect(useConnectionStore.getState().connectionState).toBe("open");
    unmount();
  });

  it("marks session restored when server pushes session_restored", () => {
    authenticate();
    const { unmount } = renderHook(() => useWebSocket());

    const ws = mocks.MockReconnectingWebSocket.instance!;
    act(() => {
      ws.emitOpen();
      ws.emitMessage(
        JSON.stringify({
          type: "system",
          action: "session_restored",
          ts: 1000,
          data: { currentLessonId: "abc" },
        }),
      );
    });

    expect(useConnectionStore.getState().sessionRestored).toBe(true);
    unmount();
  });

  it("captures system.error message into lastError", () => {
    authenticate();
    const { unmount } = renderHook(() => useWebSocket());

    const ws = mocks.MockReconnectingWebSocket.instance!;
    act(() => {
      ws.emitOpen();
      ws.emitMessage(
        JSON.stringify({
          type: "system",
          action: "error",
          ts: 1,
          data: { code: "X", message: "boom" },
        }),
      );
    });

    expect(useConnectionStore.getState().lastError).toBe("boom");
    unmount();
  });

  it("sends a heartbeat every 25s", () => {
    authenticate();
    const { unmount } = renderHook(() => useWebSocket());

    const ws = mocks.MockReconnectingWebSocket.instance!;
    act(() => {
      ws.emitOpen();
    });
    mocks.sendSpy.mockClear();

    act(() => {
      vi.advanceTimersByTime(25_000);
    });
    expect(mocks.sendSpy).toHaveBeenCalledTimes(1);
    const payload = JSON.parse(mocks.sendSpy.mock.calls[0][0] as string);
    expect(payload.type).toBe("heartbeat");
    expect(payload.data.seq).toBe(1);

    act(() => {
      vi.advanceTimersByTime(25_000);
    });
    expect(mocks.sendSpy).toHaveBeenCalledTimes(2);
    const second = JSON.parse(mocks.sendSpy.mock.calls[1][0] as string);
    expect(second.data.seq).toBe(2);

    unmount();
  });

  it("force-closes after 3 missed heartbeat acks", () => {
    authenticate();
    const { unmount } = renderHook(() => useWebSocket());

    const ws = mocks.MockReconnectingWebSocket.instance!;
    act(() => {
      ws.emitOpen();
    });

    for (let i = 0; i < 3; i++) {
      act(() => {
        vi.advanceTimersByTime(25_000);
      });
    }
    mocks.closeSpy.mockClear();
    act(() => {
      vi.advanceTimersByTime(5_000);
    });

    expect(mocks.closeSpy).toHaveBeenCalled();
    unmount();
  });

  it("missed-ack counter resets when an ack arrives", () => {
    authenticate();
    const { unmount } = renderHook(() => useWebSocket());

    const ws = mocks.MockReconnectingWebSocket.instance!;
    act(() => {
      ws.emitOpen();
    });

    for (let i = 1; i <= 2; i++) {
      act(() => {
        vi.advanceTimersByTime(25_000);
      });
      act(() => {
        ws.emitMessage(
          JSON.stringify({
            type: "heartbeat_ack",
            ts: i * 1000,
            data: { seq: i, server_ts: i * 1000 },
          }),
        );
      });
    }

    mocks.closeSpy.mockClear();
    act(() => {
      vi.advanceTimersByTime(5_000);
    });
    expect(mocks.closeSpy).not.toHaveBeenCalled();
    unmount();
  });

  it("on close code 4001 sets connectionState=closed and toasts", () => {
    authenticate();
    const { unmount } = renderHook(() => useWebSocket());

    const ws = mocks.MockReconnectingWebSocket.instance!;
    act(() => {
      ws.emitOpen();
      ws.emitClose(4001, "superseded_by_new_connection");
    });

    const state = useConnectionStore.getState();
    expect(state.connectionState).toBe("closed");
    expect(state.lastError).toBe("superseded_by_new_connection");
    expect(mocks.toastErrorSpy).toHaveBeenCalledWith(
      expect.stringContaining("another tab"),
    );
    unmount();
  });

  it("on close code 4401 sets connectionState=auth_failed and toasts", () => {
    authenticate();
    const { unmount } = renderHook(() => useWebSocket());

    const ws = mocks.MockReconnectingWebSocket.instance!;
    act(() => {
      ws.emitOpen();
      ws.emitClose(4401, "expired_token");
    });

    const state = useConnectionStore.getState();
    expect(state.connectionState).toBe("auth_failed");
    expect(mocks.toastErrorSpy).toHaveBeenCalledWith(
      expect.stringContaining("Session expired"),
    );
    unmount();
  });

  it("on close code 4401 redirects to /login after a 2s grace period", () => {
    authenticate();
    const { unmount } = renderHook(() => useWebSocket());

    const ws = mocks.MockReconnectingWebSocket.instance!;
    act(() => {
      ws.emitOpen();
      ws.emitClose(4401, "expired_token");
    });

    // No redirect yet — the grace timer is still pending.
    expect(routerPushSpy).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(routerPushSpy).toHaveBeenCalledWith("/login");
    unmount();
  });

  it("on transient close (code 1006) transitions to reconnecting", () => {
    authenticate();
    const { unmount } = renderHook(() => useWebSocket());

    const ws = mocks.MockReconnectingWebSocket.instance!;
    act(() => {
      ws.emitOpen();
      ws.emitClose(1006, "network blip");
    });

    expect(useConnectionStore.getState().connectionState).toBe("reconnecting");
    expect(useConnectionStore.getState().reconnectAttempts).toBe(1);
    unmount();
  });

  it("drops malformed inbound messages without crashing", () => {
    authenticate();
    const { unmount } = renderHook(() => useWebSocket());

    const ws = mocks.MockReconnectingWebSocket.instance!;
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    act(() => {
      ws.emitOpen();
      ws.emitMessage("not json");
      ws.emitMessage('{"ts":1}');
    });
    expect(warnSpy).toHaveBeenCalled();
    expect(useConnectionStore.getState().isConnected).toBe(true);
    warnSpy.mockRestore();
    unmount();
  });

  it("cleanup closes the socket on unmount", () => {
    authenticate();
    const { unmount } = renderHook(() => useWebSocket());
    const ws = mocks.MockReconnectingWebSocket.instance!;
    act(() => {
      ws.emitOpen();
    });
    mocks.closeSpy.mockClear();
    unmount();
    expect(mocks.closeSpy).toHaveBeenCalled();
  });

  it("does not open when enabled is false", () => {
    authenticate();
    const { unmount } = renderHook(() => useWebSocket({ enabled: false }));
    expect(mocks.MockReconnectingWebSocket.instance).toBeNull();
    unmount();
  });
});
