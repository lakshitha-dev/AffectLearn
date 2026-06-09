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

import type { BehavioralWindowPayload } from "@/types/behavioral-events";

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

/**
 * Facial-feature cycle (Story 4.2). One message per 30s cycle, regardless of
 * whether any frames were captured (`frames_b64: ""` when none — explicit signal
 * to the server to switch to behavioral-only for that cycle).
 *
 * `frames_b64` is base64 of the concatenated CHW-float32 buffer; the server
 * decodes it to `(frames_captured, 3, 96, 96)` and picks
 * `framesPerInferenceWindow` frames for the CNN-LSTM.
 *
 * Field naming: snake_case (architecture.md line 555 — WS protocol exception
 * to the REST camelCase rule).
 */
export interface FacialFeaturesMessage extends WSMessage {
  type: "facial_features";
  data: {
    cycle_number: number;
    capture_started_at: number;
    capture_ended_at: number;
    frames_captured: number;
    dropped_frames: number;
    dropped_reasons: { no_face: number; low_confidence: number };
    frames_b64: string;
    contract_version: number;
    crop_size: number;
    channel_order: "RGB";
    dtype: "float32";
  };
}

/**
 * Behavioral signal window (Story 4.3). One message per 30s cycle in any
 * non-error webcam mode — sent even for an idle window (`summary.idle: true`,
 * `events: []`) so the server treats silence as data, not absence.
 *
 * Carries RAW timed events; the backend (Story 4.4b) extracts the Bi-LSTM
 * features. Field naming: snake_case (architecture.md line 489 — WS exception
 * to the REST camelCase rule). See `behavioral-events.ts` for the schema.
 */
export interface BehavioralWindowMessage extends WSMessage {
  type: "behavioral_window";
  data: BehavioralWindowPayload;
}

export type UpstreamMessage =
  | ClientHelloMessage
  | HeartbeatMessage
  | FacialFeaturesMessage
  | BehavioralWindowMessage;

// ---------- Downstream (server → client) ----------

export interface SystemConnectedMessage extends WSMessage {
  type: "system";
  action: "connected";
  data: { welcome: boolean };
}

export interface SystemSessionRestoredMessage extends WSMessage {
  type: "system";
  action: "session_restored";
  // Field names are snake_case on the wire (architecture.md line 555 — WS exception
  // to the REST camelCase rule). Story 4.5+ populates real values; for Story 4.1
  // every field is optional because the load returns `null`.
  data: {
    current_lesson_id?: string;
    current_section_id?: string;
    last_affect_state?: unknown;
    phase?: string;
    group?: string;
    cycle_number?: number;
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
