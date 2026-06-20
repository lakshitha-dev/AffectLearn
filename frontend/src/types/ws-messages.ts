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

/**
 * Self-report affect vocabulary (Story 6.2). A deliberate 5-value SUPERSET of the backend
 * 4-value model `AFFECT_STATES` (`bored`/`confused`/`engaged`/`frustrated`) PLUS `neutral`.
 * Neutral is a self-report-only GROUND-TRUTH label, NOT a model output — a learner who feels
 * none of the 4 has a real, researchable state. Do NOT add `neutral` to the model vocabulary;
 * the 5↔4 reconciliation is a downstream research-analysis concern (Epic 6.5 / 8.6). This is
 * the single source of truth shared by `SelfReportBar` and the lesson-page consumer.
 */
export type SelfReportAffect =
  | "engaged"
  | "confused"
  | "bored"
  | "frustrated"
  | "neutral";

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

/**
 * Adaptation interaction (Story 5.6, FR22). A client→server upstream message recording
 * that the learner accepted/dismissed/applied a delivered adaptation, so the backend can
 * emit a research event for the Learner Profiler (4.5) to refine future decisions. Rides
 * the existing generic `send(msg: WSMessage)` — there is NO downstream counterpart and no
 * `ws-protocol.ts` guard change (those guards are inbound-only).
 *
 *   - `dismissed` — the learner declined the suggestion (skip_ahead "Not now" / X / Escape)
 *   - `accepted`  — the learner accepted the suggestion (skip_ahead "Skip ahead")
 *   - `applied`   — an invisible adaptation was applied client-side (increase_difficulty,
 *                   observability-only; the durable record is the server `adaptation_delivered`)
 */
export interface AdaptationInteractionMessage extends WSMessage {
  type: "adaptation_interaction";
  data: {
    adaptation_id: string;
    action: AdaptationAction;
    interaction: "dismissed" | "accepted" | "applied";
    cycle_number?: number;
  };
}

/**
 * Self-report affect (Story 6.2). The self-report twin of `adaptation_interaction`: a
 * client→server upstream message recording the learner's GROUND-TRUTH affect label (or a
 * deliberate skip) at a natural pause point, so the backend emits a `self_report` research
 * event for model validation. Rides the existing generic `send(msg: WSMessage)` — there is
 * NO downstream counterpart and no `ws-protocol.ts` guard change (those guards are
 * inbound-only).
 *
 * `affect` is the 5-value `SelfReportAffect` union — a deliberate SUPERSET of the backend
 * 4-value `AFFECT_STATES` (Neutral is a self-report-only ground-truth label, NOT a model
 * category). A deliberate skip is `{ skipped: true, affect: null }` — distinguishable from
 * missing data (a prompt the learner never reached emits NOTHING).
 */
export interface SelfReportMessage extends WSMessage {
  type: "self_report";
  data: {
    affect: SelfReportAffect | null;
    skipped: boolean;
    prompt_index?: number;
    section_id?: string;
    cycle_number?: number;
  };
}

export type UpstreamMessage =
  | ClientHelloMessage
  | HeartbeatMessage
  | FacialFeaturesMessage
  | BehavioralWindowMessage
  | AdaptationInteractionMessage
  | SelfReportMessage;

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

/**
 * Adaptation action vocabulary (Story 5.3). These are the backend `ACTION_TYPES`
 * (5.1's `fallbacks.py`) MINUS `no_action` — `no_action` never produces an
 * `adaptation` message on the wire, so it is not a valid delivered action. Keep this
 * union in lockstep with the backend vocabulary (do not invent action strings).
 */
export type AdaptationAction =
  | "show_hint"
  | "show_alternative"
  | "show_breakdown"
  | "show_encouragement"
  | "simplify"
  | "suggest_break"
  | "skip_ahead"
  | "increase_difficulty";

/**
 * Delivered adaptation (Story 5.3). The backend WS handler pushes one of these after a
 * Phase B cycle produces content. `content` is intentionally permissive — `text`/`variant`
 * for generative/selective actions, and `message` so Story 5.5's `suggest_break` variant
 * (architecture line 323) can use it without a type change. The visual rendering of these
 * is Stories 5.4–5.7; this story only routes the message into the `adaptation-store` queue.
 */
export interface AdaptationMessage extends WSMessage {
  type: "adaptation";
  action: AdaptationAction;
  content: { text?: string; variant?: string; message?: string };
}

/**
 * Notification (Story 5.7 owns the toast UX). Typed minimally here so 5.7 can extend the
 * payload without a breaking change; 5.3 only routes it through the same parsing seam.
 */
export interface NotificationMessage extends WSMessage {
  type: "notification";
  data: { level?: "info" | "success" | "warning"; message: string; [extra: string]: unknown };
}

/**
 * `system` mode_switch (Story 5.3 protocol groundwork). Flips the webcam indicator. No
 * backend code emits this yet — the real emitter is a later story; 5.3 only handles it
 * client-side. `data.mode` is the server detection-mode string mapped to a `WebcamMode`.
 */
export interface SystemModeSwitchMessage extends WSMessage {
  type: "system";
  action: "mode_switch";
  data: { mode: string };
}

/**
 * `system` reconnected (Story 5.3). Signals connection recovery so the client can clear
 * the reconnecting state / surface a brief recovery toast.
 */
export interface SystemReconnectedMessage extends WSMessage {
  type: "system";
  action: "reconnected";
  data?: Record<string, unknown>;
}

export type DownstreamMessage =
  | SystemConnectedMessage
  | SystemSessionRestoredMessage
  | SystemErrorMessage
  | SystemModeSwitchMessage
  | SystemReconnectedMessage
  | HeartbeatAckMessage
  | AdaptationMessage
  | NotificationMessage;

// ---------- Close codes (application-defined RFC 6455 range) ----------

export const WS_CLOSE_SUPERSEDED = 4001;
export const WS_CLOSE_AUTH_FAILED = 4401;
