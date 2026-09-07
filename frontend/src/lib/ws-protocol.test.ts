import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ADAPTATION_ACTIONS } from "@/types/ws-messages";
import {
  isAdaptation,
  isHeartbeatAck,
  isNotification,
  isSystemConnected,
  isSystemError,
  isSystemMessage,
  isSystemModeSwitch,
  isSystemReconnected,
  isSystemSessionRestored,
  parse,
  serialize,
} from "./ws-protocol";

describe("serialize", () => {
  it("encodes a typical envelope", () => {
    const json = serialize({ type: "heartbeat", ts: 1, data: { seq: 7 } });
    expect(JSON.parse(json)).toEqual({ type: "heartbeat", ts: 1, data: { seq: 7 } });
  });
});

describe("parse", () => {
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    warnSpy.mockRestore();
  });

  it("returns the envelope for valid JSON", () => {
    const msg = parse('{"type":"heartbeat_ack","ts":1000,"data":{"seq":5,"server_ts":1001}}');
    expect(msg).toEqual({
      type: "heartbeat_ack",
      ts: 1000,
      data: { seq: 5, server_ts: 1001 },
    });
  });

  it("returns null and warns on invalid JSON", () => {
    const msg = parse("{not json");
    expect(msg).toBeNull();
    expect(warnSpy).toHaveBeenCalled();
  });

  it("returns null when type field is missing", () => {
    const msg = parse('{"ts":1,"data":{}}');
    expect(msg).toBeNull();
    expect(warnSpy).toHaveBeenCalled();
  });

  it("returns null when ts field is missing", () => {
    const msg = parse('{"type":"heartbeat","data":{}}');
    expect(msg).toBeNull();
    expect(warnSpy).toHaveBeenCalled();
  });

  it("returns null when ts is not a number", () => {
    const msg = parse('{"type":"heartbeat","ts":"now"}');
    expect(msg).toBeNull();
    expect(warnSpy).toHaveBeenCalled();
  });

  it("accepts envelope without data field", () => {
    const msg = parse('{"type":"client_hello","ts":1}');
    expect(msg).toEqual({ type: "client_hello", ts: 1 });
  });
});

describe("type guards", () => {
  it("isHeartbeatAck only matches heartbeat_ack", () => {
    expect(isHeartbeatAck({ type: "heartbeat_ack", ts: 1, data: { seq: 1, server_ts: 1 } })).toBe(true);
    expect(isHeartbeatAck({ type: "heartbeat", ts: 1, data: { seq: 1 } })).toBe(false);
  });

  it("isSystemMessage matches any system + action message", () => {
    expect(isSystemMessage({ type: "system", action: "connected", ts: 1, data: {} } as never)).toBe(true);
    expect(isSystemMessage({ type: "system", ts: 1 } as never)).toBe(false);
    expect(isSystemMessage({ type: "heartbeat_ack", ts: 1 } as never)).toBe(false);
  });

  it("isSystemConnected matches connected only", () => {
    expect(isSystemConnected({ type: "system", action: "connected", ts: 1, data: { welcome: true } } as never)).toBe(true);
    expect(isSystemConnected({ type: "system", action: "error", ts: 1, data: {} } as never)).toBe(false);
  });

  it("isSystemSessionRestored matches session_restored only", () => {
    expect(isSystemSessionRestored({ type: "system", action: "session_restored", ts: 1, data: {} } as never)).toBe(true);
    expect(isSystemSessionRestored({ type: "system", action: "connected", ts: 1, data: { welcome: true } } as never)).toBe(false);
  });

  it("isSystemError matches error only", () => {
    expect(isSystemError({ type: "system", action: "error", ts: 1, data: { message: "x" } } as never)).toBe(true);
    expect(isSystemError({ type: "system", action: "connected", ts: 1, data: { welcome: true } } as never)).toBe(false);
  });

  it("isSystemModeSwitch matches mode_switch only", () => {
    expect(isSystemModeSwitch({ type: "system", action: "mode_switch", ts: 1, data: { mode: "behavioral_only" } } as never)).toBe(true);
    expect(isSystemModeSwitch({ type: "system", action: "error", ts: 1, data: {} } as never)).toBe(false);
    expect(isSystemModeSwitch({ type: "adaptation", action: "show_hint", ts: 1 } as never)).toBe(false);
  });

  it("isSystemReconnected matches reconnected only", () => {
    expect(isSystemReconnected({ type: "system", action: "reconnected", ts: 1 } as never)).toBe(true);
    expect(isSystemReconnected({ type: "system", action: "connected", ts: 1, data: {} } as never)).toBe(false);
  });

  it("isAdaptation requires type adaptation with a string action", () => {
    expect(isAdaptation({ type: "adaptation", action: "show_hint", ts: 1, content: { text: "hi" } } as never)).toBe(true);
    // malformed: missing action -> dropped by the guard (AC #4)
    expect(isAdaptation({ type: "adaptation", ts: 1, content: {} } as never)).toBe(false);
    // wrong type
    expect(isAdaptation({ type: "system", action: "error", ts: 1 } as never)).toBe(false);
  });

  it("isAdaptation accepts every action in the vocabulary", () => {
    // Pins the guard to the exported list rather than to a copy of it, so an action added to the
    // backend and to `ADAPTATION_ACTIONS` cannot be left unaccepted here.
    for (const action of ADAPTATION_ACTIONS) {
      expect(
        isAdaptation({ type: "adaptation", action, ts: 1, content: { text: "x" } } as never),
      ).toBe(true);
    }
  });

  it("isAdaptation drops an action outside the vocabulary, loudly", () => {
    // Previously any string passed. An unrecognised action entered the queue, matched no
    // component, rendered nothing and logged nothing — the backend recorded a delivery the
    // learner never saw, with no trace on either side.
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(
      isAdaptation({ type: "adaptation", action: "show_hnit", ts: 1, content: { text: "x" } } as never),
    ).toBe(false);
    expect(isAdaptation({ type: "adaptation", action: "no_action", ts: 1 } as never)).toBe(false);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("isNotification matches notification only", () => {
    expect(isNotification({ type: "notification", ts: 1, data: { message: "hello" } } as never)).toBe(true);
    expect(isNotification({ type: "adaptation", action: "show_hint", ts: 1 } as never)).toBe(false);
  });
});

describe("parse + guard integration", () => {
  let warnSpy: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  });
  afterEach(() => {
    warnSpy.mockRestore();
  });

  it("preserves action/content on an adaptation envelope through parse", () => {
    const msg = parse('{"type":"adaptation","action":"show_hint","ts":5,"content":{"text":"hi","variant":"show_hint"}}');
    expect(msg).not.toBeNull();
    expect(isAdaptation(msg!)).toBe(true);
  });

  it("a malformed adaptation (no action) parses but the guard rejects it", () => {
    const msg = parse('{"type":"adaptation","ts":5,"content":{}}');
    // Envelope is valid (type + ts), so parse keeps it; the guard drops it.
    expect(msg).not.toBeNull();
    expect(isAdaptation(msg!)).toBe(false);
  });
});
