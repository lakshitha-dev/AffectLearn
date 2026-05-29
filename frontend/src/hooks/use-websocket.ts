"use client";

/**
 * useWebSocket — single persistent connection per learner session.
 *
 * Architecture references:
 *   - architecture.md lines 310-328: protocol, single connection per learner, multiplexed.
 *   - architecture.md lines 350-358: reconnecting-websocket + Zustand + custom hook.
 *   - architecture.md lines 651-653: JWT in query parameter, validated once on handshake.
 *
 * Close-code semantics:
 *   - 4001 (WS_CLOSE_SUPERSEDED): server replaced us with a newer connection (second tab).
 *     The hook stops the reconnecting-websocket retry loop and surfaces a sonner toast.
 *   - 4401 (WS_CLOSE_AUTH_FAILED): token missing/invalid/expired or wrong role. Stops
 *     retrying and routes the user back to /login after a 2s grace toast (handled
 *     downstream by callers — the hook just sets `connectionState: "auth_failed"`).
 *
 * Forward-compat: only `system.connected`, `system.session_restored`, `system.error`,
 * and `heartbeat_ack` are handled here. Stories 4.2 (facial_features), 4.3 (behavioral
 * window), 5.x (adaptation, notification) will add their own listeners by consuming
 * the same connection — DO NOT open a second connection from another hook.
 */

import { useCallback, useEffect, useRef } from "react";
import { toast } from "sonner";
import ReconnectingWebSocket from "reconnecting-websocket";
import type { CloseEvent as RWSCloseEvent } from "reconnecting-websocket/dist/events";

import { useConnectionStore } from "@/stores/connection-store";
import { useSessionStore } from "@/stores/session-store";
import {
  isHeartbeatAck,
  isSystemConnected,
  isSystemError,
  isSystemSessionRestored,
  parse,
  serialize,
} from "@/lib/ws-protocol";
import {
  WS_CLOSE_AUTH_FAILED,
  WS_CLOSE_SUPERSEDED,
  type WSMessage,
} from "@/types/ws-messages";

const HEARTBEAT_INTERVAL_MS = 25_000;
const HEARTBEAT_TIMEOUT_MS = 5_000;
const MAX_MISSED_HEARTBEATS = 3;

const RWS_OPTIONS = {
  minReconnectionDelay: 1000,
  maxReconnectionDelay: 30_000,
  reconnectionDelayGrowFactor: 2,
  connectionTimeout: 4000,
  maxRetries: Infinity,
} as const;

interface UseWebSocketOptions {
  enabled?: boolean;
}

interface UseWebSocketReturn {
  send: (msg: WSMessage) => void;
  close: () => void;
}

function buildWsUrl(): string | null {
  const base = process.env.NEXT_PUBLIC_WS_URL;
  if (!base) return null;

  const accessToken = useSessionStore.getState().accessToken;
  if (!accessToken) return null;

  return `${base}/api/v1/ws?token=${encodeURIComponent(accessToken)}`;
}

export function useWebSocket(
  options: UseWebSocketOptions = {},
): UseWebSocketReturn {
  const { enabled = true } = options;

  const wsRef = useRef<ReconnectingWebSocket | null>(null);
  const heartbeatIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const heartbeatTimeoutsRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());
  const seqRef = useRef<number>(0);
  const missedHeartbeatsRef = useRef<number>(0);
  const giveUpRef = useRef<boolean>(false);

  const send = useCallback((msg: WSMessage) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== ReconnectingWebSocket.OPEN) {
      return;
    }
    ws.send(serialize(msg));
  }, []);

  const close = useCallback(() => {
    giveUpRef.current = true;
    wsRef.current?.close();
  }, []);

  useEffect(() => {
    if (!enabled) return;

    const isAuthed = useSessionStore.getState().accessToken !== null;
    if (!isAuthed) return;

    const store = useConnectionStore.getState();
    store.reset();
    store.setConnectionState("connecting");

    // Expose the connection store on window for E2E inspection (Playwright reads it
    // via page.evaluate to assert isConnected / connectionState transitions).
    if (typeof window !== "undefined") {
      (window as unknown as { __connectionStore?: typeof useConnectionStore }).__connectionStore =
        useConnectionStore;
    }

    // URL provider lets reconnecting-websocket pick up a fresh JWT on every retry.
    // The library's typings accept either a string or a () => string. If the user logs
    // out mid-session the provider can return an empty string, which will cause RWS
    // to fail and emit `onerror` — fine, the connection will surface as auth_failed.
    const urlProvider = (): string => buildWsUrl() ?? "";

    const ws = new ReconnectingWebSocket(urlProvider, [], RWS_OPTIONS);
    wsRef.current = ws;

    const startHeartbeat = () => {
      stopHeartbeat();
      heartbeatIntervalRef.current = setInterval(() => {
        if (ws.readyState !== ReconnectingWebSocket.OPEN) return;

        seqRef.current += 1;
        const seq = seqRef.current;
        ws.send(serialize({ type: "heartbeat", ts: Date.now(), data: { seq } }));

        const timeout = setTimeout(() => {
          heartbeatTimeoutsRef.current.delete(seq);
          missedHeartbeatsRef.current += 1;
          if (missedHeartbeatsRef.current >= MAX_MISSED_HEARTBEATS) {
            // Force a close — reconnecting-websocket will reconnect (unless give-up flag set).
            ws.close();
          }
        }, HEARTBEAT_TIMEOUT_MS);
        heartbeatTimeoutsRef.current.set(seq, timeout);
      }, HEARTBEAT_INTERVAL_MS);
    };

    const stopHeartbeat = () => {
      if (heartbeatIntervalRef.current) {
        clearInterval(heartbeatIntervalRef.current);
        heartbeatIntervalRef.current = null;
      }
      heartbeatTimeoutsRef.current.forEach((t) => clearTimeout(t));
      heartbeatTimeoutsRef.current.clear();
    };

    const handleOpen = () => {
      const s = useConnectionStore.getState();
      s.setConnected(true);
      s.setConnectionState("open");
      s.setError(null);
      s.resetReconnect();
      missedHeartbeatsRef.current = 0;
      startHeartbeat();
    };

    const handleMessage = (event: MessageEvent) => {
      const raw = typeof event.data === "string" ? event.data : "";
      const msg = parse(raw);
      if (!msg) return;

      if (isHeartbeatAck(msg)) {
        const seq = msg.data.seq;
        if (typeof seq === "number") {
          const t = heartbeatTimeoutsRef.current.get(seq);
          if (t) {
            clearTimeout(t);
            heartbeatTimeoutsRef.current.delete(seq);
          }
        }
        missedHeartbeatsRef.current = 0;
        return;
      }

      if (isSystemConnected(msg)) {
        // Already handled in handleOpen; nothing extra to do unless server attaches data.
        return;
      }

      if (isSystemSessionRestored(msg)) {
        useConnectionStore.getState().markSessionRestored();
        return;
      }

      if (isSystemError(msg)) {
        useConnectionStore
          .getState()
          .setError(msg.data?.message ?? msg.data?.code ?? "ws_error");
        return;
      }

      // Unknown but well-formed types (future-proof): silently dropped — `parse` already validated shape.
    };

    const handleClose = (event: RWSCloseEvent) => {
      stopHeartbeat();
      const s = useConnectionStore.getState();
      s.setConnected(false);

      if (event.code === WS_CLOSE_SUPERSEDED) {
        giveUpRef.current = true;
        s.setConnectionState("closed");
        s.setError("superseded_by_new_connection");
        toast.error("Your session is open in another tab. Close that tab to return here.");
        try {
          ws.close();
        } catch {
          // already closing
        }
        return;
      }

      if (event.code === WS_CLOSE_AUTH_FAILED) {
        giveUpRef.current = true;
        s.setConnectionState("auth_failed");
        s.setError(event.reason || "auth_failed");
        toast.error("Session expired. Please log in again.");
        try {
          ws.close();
        } catch {
          // already closing
        }
        return;
      }

      if (giveUpRef.current) {
        s.setConnectionState("closed");
        return;
      }

      // Transient drop — RWS will retry.
      s.setConnectionState("reconnecting");
      s.incrementReconnect();
    };

    const handleError = () => {
      // RWS will emit this on each failed retry — don't toast or set auth_failed here;
      // the close handler decides those based on close code.
      useConnectionStore.getState().setError("ws_transport_error");
    };

    ws.addEventListener("open", handleOpen);
    ws.addEventListener("message", handleMessage);
    ws.addEventListener("close", handleClose);
    ws.addEventListener("error", handleError);

    return () => {
      stopHeartbeat();
      giveUpRef.current = true;
      ws.removeEventListener("open", handleOpen);
      ws.removeEventListener("message", handleMessage);
      ws.removeEventListener("close", handleClose);
      ws.removeEventListener("error", handleError);
      ws.close();
      wsRef.current = null;
      seqRef.current = 0;
      missedHeartbeatsRef.current = 0;
      useConnectionStore.getState().reset();
    };
  }, [enabled]);

  return { send, close };
}
