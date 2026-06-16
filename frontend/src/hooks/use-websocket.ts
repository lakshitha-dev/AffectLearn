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
 * Handled inbound messages: `heartbeat_ack`; `system.connected` / `system.session_restored`
 * / `system.error` / `system.mode_switch` (flips the webcam indicator) / `system.reconnected`
 * (clears reconnecting state); `adaptation` (routed into the `adaptation-store` queue); and
 * `notification` (groundwork seam for Story 5.7). Stories 4.2 (facial_features) / 4.3
 * (behavioral window) send on this same connection — DO NOT open a second connection from
 * another hook.
 *
 * Story 5.3 scope: this hook only ROUTES adaptations into the queue. The VISUAL rendering
 * (hint callout, break card, skip UI, notification toasts) is Stories 5.4–5.7, which
 * consume `useAdaptationStore`.
 */

import { useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import ReconnectingWebSocket from "reconnecting-websocket";
import type { CloseEvent as RWSCloseEvent } from "reconnecting-websocket/dist/events";

import { useConnectionStore } from "@/stores/connection-store";
import { useSessionStore } from "@/stores/session-store";
import { useWebcamStore, type WebcamMode } from "@/stores/webcam-store";
import { useAdaptationStore, type Adaptation } from "@/stores/adaptation-store";
import { refreshAccessToken } from "@/lib/api-client";
import {
  isAdaptation,
  isHeartbeatAck,
  isNotification,
  isSystemConnected,
  isSystemError,
  isSystemModeSwitch,
  isSystemReconnected,
  isSystemSessionRestored,
  parse,
  serialize,
} from "@/lib/ws-protocol";
import {
  WS_CLOSE_AUTH_FAILED,
  WS_CLOSE_SUPERSEDED,
  type AdaptationMessage,
  type WSMessage,
} from "@/types/ws-messages";

/** Stable id for a queued adaptation; falls back to a counter if crypto is unavailable. */
let _adaptationSeq = 0;
function _adaptationId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  _adaptationSeq += 1;
  return `adaptation-${Date.now()}-${_adaptationSeq}`;
}

/** Map an inbound `adaptation` message to a queue item (no rendering — Stories 5.4–5.7). */
function mapToAdaptation(msg: AdaptationMessage): Adaptation {
  return {
    id: _adaptationId(),
    action: msg.action,
    text: msg.content?.text,
    variant: msg.content?.variant,
    receivedAt: Date.now(),
  };
}

/**
 * Map the server `system.mode_switch` mode string to a client `WebcamMode`. The server
 * may send either a `WebcamMode` directly (`adaptive`/`behavioral`/`error`) or its
 * detection-mode vocabulary (`multimodal`/`facial_only` → adaptive; `behavioral_only` →
 * behavioral). Unknown values fall back to `behavioral` (the safe non-webcam mode).
 */
function mapMode(mode: string): WebcamMode {
  switch (mode) {
    case "adaptive":
    case "multimodal":
    case "facial_only":
      return "adaptive";
    case "error":
      return "error";
    case "behavioral":
    case "behavioral_only":
    default:
      return "behavioral";
  }
}

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

/**
 * Build the WS URL for a (re)connect. Per AC #5 this:
 *   1. Calls `refreshAccessToken()` first if the stored access token is within the
 *      refresh window (`shouldRefresh()` — currently 5 min before expiry).
 *   2. Reads a fresh `accessToken` from the session store.
 *   3. Returns `null` if no token is available — the caller must give up rather
 *      than retry with an empty URL.
 *
 * `refreshAccessToken()` shares its in-flight-promise dedup with `api-client.ts`,
 * so concurrent REST + WS refresh attempts collapse to a single network call.
 */
async function buildWsUrl(): Promise<string | null> {
  const base = process.env.NEXT_PUBLIC_WS_URL;
  if (!base) return null;

  const session = useSessionStore.getState();
  if (session.shouldRefresh()) {
    await refreshAccessToken();
  }

  const accessToken = useSessionStore.getState().accessToken;
  if (!accessToken) return null;

  return `${base}/api/v1/ws?token=${encodeURIComponent(accessToken)}`;
}

export function useWebSocket(
  options: UseWebSocketOptions = {},
): UseWebSocketReturn {
  const { enabled = true } = options;

  const router = useRouter();
  const wsRef = useRef<ReconnectingWebSocket | null>(null);
  const heartbeatIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const heartbeatTimeoutsRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());
  const seqRef = useRef<number>(0);
  const missedHeartbeatsRef = useRef<number>(0);
  const giveUpRef = useRef<boolean>(false);

  const send = useCallback((msg: WSMessage) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== ReconnectingWebSocket.OPEN) {
      // Dropping is intentional during reconnects, but future stories (4.2 facial
      // features, 4.3 behavioral windows) send on this hook at high frequency —
      // surface drops so they can be investigated rather than silently lost.
      console.warn("[ws] send dropped — socket not OPEN", { type: msg.type });
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

    // Check token freshness, not just presence — a persisted-but-expired token
    // would otherwise immediately bounce off a 4401 close on connect.
    if (!useSessionStore.getState().isAuthenticated()) return;

    const store = useConnectionStore.getState();
    store.reset();
    store.setConnectionState("connecting");

    // Expose the connection store on window for E2E inspection (Playwright reads it
    // via page.evaluate to assert isConnected / connectionState transitions).
    // Dev/test only — production builds should not leak internal state.
    if (
      typeof window !== "undefined" &&
      process.env.NODE_ENV !== "production"
    ) {
      (window as unknown as { __connectionStore?: typeof useConnectionStore }).__connectionStore =
        useConnectionStore;
    }

    // URL provider runs on every (re)connect attempt — refreshes the JWT first so
    // a long-lived session never sends an expired token. `reconnecting-websocket`
    // accepts either a sync or async URL provider and awaits the promise.
    const urlProvider = (): Promise<string> =>
      buildWsUrl().then((url) => {
        if (url === null) {
          // No token available — flip the give-up flag and surface auth_failed.
          // Returning "" causes RWS to throw on `new WebSocket("")`, which we
          // intercept via the close handler below.
          giveUpRef.current = true;
          useConnectionStore.getState().setConnectionState("auth_failed");
          return "";
        }
        return url;
      });

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

      // Story 5.3: `system.mode_switch` flips the webcam indicator (no backend emitter
      // yet — protocol groundwork; the real emitter is a later story).
      if (isSystemModeSwitch(msg)) {
        useWebcamStore.getState().setMode(mapMode(msg.data.mode));
        return;
      }

      // Story 5.3: `system.reconnected` clears reconnecting state / surfaces a recovery.
      if (isSystemReconnected(msg)) {
        const s = useConnectionStore.getState();
        s.setError(null);
        s.resetReconnect();
        return;
      }

      // Story 5.3: route a delivered adaptation into the queue. NO visual component
      // renders here — Stories 5.4–5.7 consume `useAdaptationStore`.
      if (isAdaptation(msg)) {
        useAdaptationStore.getState().pushAdaptation(mapToAdaptation(msg));
        return;
      }

      // Story 5.3: `notification` parses through the same seam (groundwork for 5.7's
      // toast UX — no toast is built here).
      if (isNotification(msg)) {
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
        // Grace period so the toast is readable before the redirect.
        setTimeout(() => router.push("/login"), 2000);
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
