/**
 * WebSocket message types for the affect detection / agent loop.
 *
 * Protocol (architecture.md lines 310-328, 489, 543-545):
 *  - JSON with `type` discriminator (snake_case both directions — this is the
 *    documented exception to the REST API's camelCase-on-the-wire rule).
 *  - `ts` is a Unix timestamp in milliseconds (NOT ISO 8601 — REST uses ISO).
 *  - For `type: "system"`, the sub-discriminator is `action` (per Story 4.1 Deviation 2).
 *  - For all other types, `type` alone is the discriminator.
 *
 * Future stories (4.2, 4.3, 5.x) extend the upstream/downstream unions without modifying
 * use-websocket.ts.
 */

export interface WSMessage {
  type: string;
  ts: number;
  data?: unknown;
}

// ---------- Upstream (client → server) ----------

export interface ClientHelloMessage extends WSMessage {
  type: "client_hello";
  data?: { client_version?: string };
}

export interface HeartbeatMessage extends WSMessage {
  type: "heartbeat";
  data: { seq: number };
}

export type UpstreamMessage = ClientHelloMessage | HeartbeatMessage;

// ---------- Downstream (server → client) ----------

export interface SystemConnectedMessage extends WSMessage {
  type: "system";
  action: "connected";
  data: { welcome: boolean };
}

export interface SystemSessionRestoredMessage extends WSMessage {
  type: "system";
  action: "session_restored";
  data: {
    currentLessonId?: string;
    currentSectionId?: string;
    lastAffectState?: unknown;
    phase?: string;
    group?: string;
    cycleNumber?: number;
    // Forward-compat: accept any additional keys without breaking parsing.
    [extra: string]: unknown;
  };
}

export interface SystemErrorMessage extends WSMessage {
  type: "system";
  action: "error";
  data: { code?: string; message?: string };
}

export interface HeartbeatAckMessage extends WSMessage {
  type: "heartbeat_ack";
  data: { seq: number | null; server_ts: number };
}

export type DownstreamMessage =
  | SystemConnectedMessage
  | SystemSessionRestoredMessage
  | SystemErrorMessage
  | HeartbeatAckMessage;

// ---------- Close codes (application-defined RFC 6455 range) ----------

export const WS_CLOSE_SUPERSEDED = 4001;
export const WS_CLOSE_AUTH_FAILED = 4401;
