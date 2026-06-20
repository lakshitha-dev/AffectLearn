import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

const mocks = vi.hoisted(() => {
  const loadFaceDetectorSpy = vi.fn();
  const cropAndNormalizeSpy = vi.fn();
  const framesToBase64Spy = vi.fn();
  const detectorCloseSpy = vi.fn();
  const detectForVideoSpy = vi.fn();

  return {
    loadFaceDetectorSpy,
    cropAndNormalizeSpy,
    framesToBase64Spy,
    detectorCloseSpy,
    detectForVideoSpy,
  };
});

vi.mock("@/lib/mediapipe-loader", () => ({
  loadFaceDetector: mocks.loadFaceDetectorSpy,
}));

vi.mock("@/lib/preprocess", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/preprocess")>("@/lib/preprocess");
  return {
    ...actual,
    cropAndNormalize: mocks.cropAndNormalizeSpy,
    framesToBase64: mocks.framesToBase64Spy,
  };
});

import { useMediaPipe } from "./use-media-pipe";
import { useWebcamStore } from "@/stores/webcam-store";
import { useConnectionStore } from "@/stores/connection-store";
import type { WSMessage } from "@/types/ws-messages";

type SendFn = (msg: WSMessage) => void;
type SendMock = ReturnType<typeof vi.fn> & SendFn;
const makeSend = (): SendMock => vi.fn() as unknown as SendMock;

// ---- Test plumbing ----------------------------------------------------------

interface MockTrack {
  stop: ReturnType<typeof vi.fn>;
  addEventListener: ReturnType<typeof vi.fn>;
  removeEventListener: ReturnType<typeof vi.fn>;
  endedHandlers: Array<() => void>;
}

function makeTrack(): MockTrack {
  const track: MockTrack = {
    stop: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    endedHandlers: [],
  };
  track.addEventListener.mockImplementation(
    (event: string, handler: () => void) => {
      if (event === "ended") track.endedHandlers.push(handler);
    },
  );
  return track;
}

interface MockStream {
  getTracks: () => MockTrack[];
  _tracks: MockTrack[];
}

function makeStream(): MockStream {
  const tracks = [makeTrack()];
  return {
    _tracks: tracks,
    getTracks: () => tracks,
  };
}

function makeDetector(score: number, withBbox = true) {
  return {
    close: mocks.detectorCloseSpy,
    detectForVideo: mocks.detectForVideoSpy.mockReturnValue({
      detections: withBbox
        ? [
            {
              categories: [{ score }],
              boundingBox: {
                originX: 10,
                originY: 10,
                width: 100,
                height: 100,
              },
            },
          ]
        : [],
    }),
  };
}

// ---- Suite ------------------------------------------------------------------

describe("useMediaPipe", () => {
  let getUserMediaMock: ReturnType<typeof vi.fn>;
  let stream: MockStream;
  let send: SendMock;
  let originalDescriptor: PropertyDescriptor | undefined;

  beforeEach(() => {
    vi.useFakeTimers();

    mocks.loadFaceDetectorSpy.mockReset();
    mocks.cropAndNormalizeSpy.mockReset();
    mocks.framesToBase64Spy.mockReset();
    mocks.detectorCloseSpy.mockReset();
    mocks.detectForVideoSpy.mockReset();

    // Default: a usable face, a usable detector.
    mocks.loadFaceDetectorSpy.mockResolvedValue(makeDetector(0.9));
    mocks.cropAndNormalizeSpy.mockReturnValue(new Float32Array(27648));
    mocks.framesToBase64Spy.mockReturnValue("BASE64_FRAMES");

    stream = makeStream();
    getUserMediaMock = vi.fn().mockResolvedValue(stream);

    originalDescriptor = Object.getOwnPropertyDescriptor(
      navigator,
      "mediaDevices",
    );
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: getUserMediaMock },
    });

    // HTMLVideoElement.play & readyState aren't implemented in jsdom — stub them.
    Object.defineProperty(HTMLMediaElement.prototype, "play", {
      configurable: true,
      value: vi.fn().mockResolvedValue(undefined),
    });
    Object.defineProperty(HTMLMediaElement.prototype, "readyState", {
      configurable: true,
      get: () => 4, // HAVE_ENOUGH_DATA
    });

    send = makeSend();

    useWebcamStore.setState({ mode: "behavioral", calibrated: false });
    useConnectionStore.setState({
      isConnected: true,
      connectionState: "open",
      lastError: null,
      reconnectAttempts: 0,
      sessionRestored: false,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    if (originalDescriptor) {
      Object.defineProperty(navigator, "mediaDevices", originalDescriptor);
    }
  });

  // -- AC #3 & #7: inertness ----

  it("does NOT call getUserMedia when mode === 'behavioral'", async () => {
    useWebcamStore.setState({ mode: "behavioral" });
    renderHook(() => useMediaPipe({ send }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(getUserMediaMock).not.toHaveBeenCalled();
    expect(mocks.loadFaceDetectorSpy).not.toHaveBeenCalled();
  });

  it("does NOT call getUserMedia when mode === 'error'", async () => {
    useWebcamStore.setState({ mode: "error" });
    renderHook(() => useMediaPipe({ send }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(getUserMediaMock).not.toHaveBeenCalled();
  });

  it("does NOT call getUserMedia when enabled === false even if mode is adaptive", async () => {
    useWebcamStore.setState({ mode: "adaptive" });
    renderHook(() => useMediaPipe({ send, enabled: false }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(getUserMediaMock).not.toHaveBeenCalled();
  });

  // -- AC #3 & #4: activation ----

  it("acquires the stream, loads the detector, and starts capture when mode === 'adaptive'", async () => {
    useWebcamStore.setState({ mode: "adaptive" });
    renderHook(() => useMediaPipe({ send, captureMs: 100, cycleMs: 1000 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });

    expect(getUserMediaMock).toHaveBeenCalledWith({ video: true });
    expect(mocks.loadFaceDetectorSpy).toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });

    expect(mocks.detectForVideoSpy).toHaveBeenCalled();
    expect(mocks.cropAndNormalizeSpy).toHaveBeenCalled();
  });

  it("drops a frame with score < 0.5 as low_confidence (no crop, no push)", async () => {
    mocks.loadFaceDetectorSpy.mockResolvedValueOnce(makeDetector(0.3));
    useWebcamStore.setState({ mode: "adaptive" });

    renderHook(() => useMediaPipe({ send, captureMs: 100, cycleMs: 10_000 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });

    expect(mocks.detectForVideoSpy).toHaveBeenCalled();
    expect(mocks.cropAndNormalizeSpy).not.toHaveBeenCalled();
  });

  it("drops a frame with no detection as no_face", async () => {
    mocks.loadFaceDetectorSpy.mockResolvedValueOnce(makeDetector(0.0, false));
    useWebcamStore.setState({ mode: "adaptive" });

    renderHook(() => useMediaPipe({ send, captureMs: 100, cycleMs: 10_000 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });

    expect(mocks.cropAndNormalizeSpy).not.toHaveBeenCalled();
  });

  // -- AC #5: cycle send ----

  it("at cycle boundary, sends a facial_features message with the captured frames", async () => {
    useWebcamStore.setState({ mode: "adaptive" });

    renderHook(() => useMediaPipe({ send, captureMs: 100, cycleMs: 500 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    // 5 capture ticks (5 successful frames) before the cycle fires at 500ms.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(send).toHaveBeenCalledTimes(1);
    const msg = send.mock.calls[0][0];
    expect(msg.type).toBe("facial_features");
    expect(msg.data.cycle_number).toBe(1);
    expect(msg.data.frames_captured).toBeGreaterThanOrEqual(4);
    expect(msg.data.dropped_frames).toBe(0);
    expect(msg.data.contract_version).toBe(1);
    expect(msg.data.crop_size).toBe(96);
    expect(msg.data.channel_order).toBe("RGB");
    expect(msg.data.dtype).toBe("float32");
    expect(msg.data.frames_b64).toBe("BASE64_FRAMES");
  });

  it("sends frames_b64: '' when no frames were captured (entire cycle dropped)", async () => {
    mocks.loadFaceDetectorSpy.mockResolvedValueOnce(makeDetector(0.0, false));
    useWebcamStore.setState({ mode: "adaptive" });

    renderHook(() => useMediaPipe({ send, captureMs: 100, cycleMs: 300 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(send).toHaveBeenCalledTimes(1);
    const msg = send.mock.calls[0][0];
    expect(msg.data.frames_captured).toBe(0);
    expect(msg.data.frames_b64).toBe("");
    expect(msg.data.dropped_frames).toBeGreaterThan(0);
  });

  it("increments cycle_number on each subsequent cycle", async () => {
    useWebcamStore.setState({ mode: "adaptive" });

    renderHook(() => useMediaPipe({ send, captureMs: 100, cycleMs: 300 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(send).toHaveBeenCalledTimes(2);
    expect(send.mock.calls[0][0].data.cycle_number).toBe(1);
    expect(send.mock.calls[1][0].data.cycle_number).toBe(2);
  });

  // -- AC #8: stream failure ----

  it("on track 'ended', sets webcam mode to 'error' and stops sending", async () => {
    useWebcamStore.setState({ mode: "adaptive" });

    renderHook(() => useMediaPipe({ send, captureMs: 100, cycleMs: 500 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });

    // Fire the ended event.
    act(() => {
      stream._tracks[0].endedHandlers.forEach((h) => h());
    });

    expect(useWebcamStore.getState().mode).toBe("error");
    expect(stream._tracks[0].stop).toHaveBeenCalled();

    // No further sends.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(send).not.toHaveBeenCalled();
  });

  // -- AC #9: backpressure ----

  it("drops the cycle (does not send) when isConnected === false", async () => {
    useWebcamStore.setState({ mode: "adaptive" });
    useConnectionStore.setState({ isConnected: false });

    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    renderHook(() => useMediaPipe({ send, captureMs: 100, cycleMs: 300 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(send).not.toHaveBeenCalled();
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("facial_cycle_dropped_no_ws"),
      1,
    );

    warnSpy.mockRestore();
  });

  // -- AC #3: cleanup on unmount ----

  it("stops all tracks and clears intervals on unmount", async () => {
    useWebcamStore.setState({ mode: "adaptive" });

    const { unmount } = renderHook(() =>
      useMediaPipe({ send, captureMs: 100, cycleMs: 1000 }),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });

    const track = stream._tracks[0];
    expect(track.stop).not.toHaveBeenCalled();

    unmount();

    expect(track.stop).toHaveBeenCalled();
    expect(track.removeEventListener).toHaveBeenCalledWith(
      "ended",
      expect.any(Function),
    );

    // After unmount the cycle interval must not fire.
    const sendCountBefore = send.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(send.mock.calls.length).toBe(sendCountBefore);
  });

  it("tears down when mode transitions away from 'adaptive'", async () => {
    useWebcamStore.setState({ mode: "adaptive" });

    renderHook(() => useMediaPipe({ send, captureMs: 100, cycleMs: 1000 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    const track = stream._tracks[0];

    act(() => {
      useWebcamStore.setState({ mode: "behavioral" });
    });

    expect(track.stop).toHaveBeenCalled();
  });

  // -- Privacy verification (AC #10) ----

  it("never writes to localStorage, sessionStorage, or IndexedDB during a cycle", async () => {
    useWebcamStore.setState({ mode: "adaptive" });

    const lsSetItem = vi.spyOn(Storage.prototype, "setItem");
    // AC10: also guard IndexedDB — spy on the open() entry point (all IDB writes
    // require an open() call). jsdom may not implement indexedDB; if unavailable,
    // the assertion is vacuously satisfied (the hook can't use a missing API).
    const idbOpen =
      typeof globalThis.indexedDB !== "undefined"
        ? vi.spyOn(globalThis.indexedDB, "open")
        : null;

    renderHook(() => useMediaPipe({ send, captureMs: 100, cycleMs: 300 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });

    expect(lsSetItem).not.toHaveBeenCalled();
    if (idbOpen) {
      expect(idbOpen).not.toHaveBeenCalled();
      idbOpen.mockRestore();
    }
    lsSetItem.mockRestore();
  });

  // -- WS payload shape ----

  it("WS payload contains base64 frames and snake_case fields per protocol", async () => {
    useWebcamStore.setState({ mode: "adaptive" });

    renderHook(() => useMediaPipe({ send, captureMs: 100, cycleMs: 300 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    const msg = send.mock.calls[0][0];
    expect(Object.keys(msg.data)).toEqual(
      expect.arrayContaining([
        "cycle_number",
        "capture_started_at",
        "capture_ended_at",
        "frames_captured",
        "dropped_frames",
        "dropped_reasons",
        "frames_b64",
        "contract_version",
        "crop_size",
        "channel_order",
        "dtype",
      ]),
    );
    expect(typeof msg.data.frames_b64).toBe("string");
  });
});
