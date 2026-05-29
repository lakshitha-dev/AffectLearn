import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  isHeartbeatAck,
  isSystemConnected,
  isSystemError,
  isSystemMessage,
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
});
