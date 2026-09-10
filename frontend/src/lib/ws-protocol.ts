/**
 * Serialise / parse WebSocket messages on the wire.
 *
 * The base envelope is `{type: string, ts: number, data?: unknown}`. We validate with
 * Zod and drop anything that doesn't match — the connection stays open per AC #8.
 * Caller (use-websocket.ts) narrows the resulting `WSMessage` by `type` (and `action`
 * for `type === "system"`) to one of the discriminated unions in ws-messages.ts.
 */

import { z } from "zod";

import { ADAPTATION_ACTIONS } from "@/types/ws-messages";
import type { DownstreamMessage, WSMessage } from "@/types/ws-messages";

const RAW_LOG_MAX = 200;

// Use `.loose()` (Zod v4) / `.passthrough()` (Zod v3) so top-level fields beyond
// {type, ts, data} survive parsing — required for system messages that carry an `action`
// sub-discriminator, and for forward-compat with future protocol additions.
const wsEnvelopeSchema = z
  .object({
    type: z.string(),
    ts: z.number(),
    data: z.unknown().optional(),
  })
  .loose();

export function serialize(msg: WSMessage): string {
  return JSON.stringify(msg);
}

/**
 * Parse a raw WS payload. Returns null on any parse/validation failure and emits a
 * single `console.warn` with the raw payload truncated.
 */
export function parse(raw: string): WSMessage | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    console.warn("[ws] dropped non-json message", raw.slice(0, RAW_LOG_MAX));
    return null;
  }

  const result = wsEnvelopeSchema.safeParse(parsed);
  if (!result.success) {
    console.warn("[ws] dropped invalid envelope", raw.slice(0, RAW_LOG_MAX));
    return null;
  }

  return result.data as WSMessage;
}

// ---------- Type guards ----------

export function isHeartbeatAck(
  msg: WSMessage,
): msg is Extract<DownstreamMessage, { type: "heartbeat_ack" }> {
  return msg.type === "heartbeat_ack";
}

export function isSystemMessage(
  msg: WSMessage,
): msg is Extract<DownstreamMessage, { type: "system" }> {
  return msg.type === "system" && typeof (msg as { action?: unknown }).action === "string";
}

export function isSystemConnected(
  msg: WSMessage,
): msg is Extract<DownstreamMessage, { type: "system"; action: "connected" }> {
  return isSystemMessage(msg) && msg.action === "connected";
}

export function isSystemSessionRestored(
  msg: WSMessage,
): msg is Extract<DownstreamMessage, { type: "system"; action: "session_restored" }> {
  return isSystemMessage(msg) && msg.action === "session_restored";
}

export function isSystemError(
  msg: WSMessage,
): msg is Extract<DownstreamMessage, { type: "system"; action: "error" }> {
  return isSystemMessage(msg) && msg.action === "error";
}

export function isSystemModeSwitch(
  msg: WSMessage,
): msg is Extract<DownstreamMessage, { type: "system"; action: "mode_switch" }> {
  return isSystemMessage(msg) && msg.action === "mode_switch";
}

export function isSystemReconnected(
  msg: WSMessage,
): msg is Extract<DownstreamMessage, { type: "system"; action: "reconnected" }> {
  return isSystemMessage(msg) && msg.action === "reconnected";
}

const KNOWN_ADAPTATION_ACTIONS: ReadonlySet<string> = new Set(ADAPTATION_ACTIONS);

// Story 5.3: `adaptation` requires a string `action` (a malformed one missing `action`
// is dropped here without breaking the connection — AC #4). The visual rendering of the
// queued adaptation is Stories 5.4–5.7; this guard only feeds the routing seam.
//
// The action must also be one the client knows. Accepting any string let an unrecognised
// action — a backend vocabulary change, a typo in a hand-sent payload — into the queue, where
// it matched no component, rendered nothing, and logged nothing: an intervention the backend
// records as delivered that the learner never saw, with no trace on either side. Dropping it
// here is the same treatment a malformed envelope gets, and it says so out loud.
export function isAdaptation(
  msg: WSMessage,
): msg is Extract<DownstreamMessage, { type: "adaptation" }> {
  if (msg.type !== "adaptation") return false;
  const action = (msg as { action?: unknown }).action;
  if (typeof action !== "string") return false;
  if (!KNOWN_ADAPTATION_ACTIONS.has(action)) {
    console.warn("[ws] dropped adaptation with unknown action", action.slice(0, RAW_LOG_MAX));
    return false;
  }
  return true;
}

export function isNotification(
  msg: WSMessage,
): msg is Extract<DownstreamMessage, { type: "notification" }> {
  return msg.type === "notification";
}
