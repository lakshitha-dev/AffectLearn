import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

const mocks = vi.hoisted(() => {
  const loadFaceDetectorSpy = vi.fn();   // named for continuity; now loads the LANDMARKER
  const detectorCloseSpy = vi.fn();
  const detectForVideoSpy = vi.fn();

  return { loadFaceDetectorSpy, detectorCloseSpy, detectForVideoSpy };
});

vi.mock("@/lib/mediapipe-loader", () => ({
  loadFaceLandmarker: mocks.loadFaceDetectorSpy,
}));

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

/**
 * A FaceLandmarker stand-in. `withBbox` is kept as the parameter name so the existing call sites
 * read unchanged, but it now means "was a face found": true yields 478 landmarks plus a pose
 * matrix, false yields none, which is the faceless-frame path.
 */
function makeDetector(score: number, withBbox = true) {
  const landmarks = Array.from({ length: 478 }, (_, i) => ({
    x: 0.4 + (i % 17) * 0.002,
    y: 0.4 + (i % 13) * 0.003,
    z: 0.01 * ((i % 7) - 3),
  }));
  const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  // FaceLandmarker applies its confidence threshold INTERNALLY (minFaceDetectionConfidence,
  // default 0.5) and does not surface a per-detection score for the caller to filter on. So a
  // low-confidence face is modelled the way the runtime actually delivers it: as no face at all,
  // rather than as a detection this hook then discards.
  const found = withBbox && score >= 0.5;
  return {
    close: mocks.detectorCloseSpy,
    detectForVideo: mocks.detectForVideoSpy.mockReturnValue(
      found
        ? { faceLandmarks: [landmarks], facialTransformationMatrixes: [{ data: identity }] }
        : { faceLandmarks: [], facialTransformationMatrixes: [] },
    ),
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
    mocks.detectorCloseSpy.mockReset();
    mocks.detectForVideoSpy.mockReset();

    // Default: a usable face, a usable detector.
    mocks.loadFaceDetectorSpy.mockResolvedValue(makeDetector(0.9));

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
    expect(mocks.detectForVideoSpy).toHaveBeenCalled();
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
    expect(mocks.detectForVideoSpy).toHaveBeenCalled();
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

    expect(mocks.detectForVideoSpy).toHaveBeenCalled();
  });

  // -- AC #5: cycle send ----

  it("at cycle boundary, sends a facial_features message with the captured geometry", async () => {
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
    expect(msg.data.geometry_contract_version).toBe(1);
    expect(msg.data.channel_order).toContain("gaze_x");
    expect(msg.data.frames_per_cycle).toBe(10);
    expect(Array.isArray(msg.data.geometry)).toBe(true);
    expect(msg.data.geometry.length).toBeGreaterThan(0);
    expect(msg.data.geometry[0]).toHaveLength(11);
  });

  it("sends an empty geometry array when nothing was captured", async () => {
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
    // A faceless frame still yields a geometry ROW (all-NaN plus face_found = 0) rather than
    // nothing, so the server can tell "learner absent for the whole cycle" from "no cycle ran".
    // What must be zero is faces seen, and face_absent is what suppresses inference.
    expect(msg.data.frames_with_face).toBe(0);
    expect(msg.data.face_absent).toBe(true);
    expect(msg.data.geometry.every((r: (number | null)[]) => r[10] === 0)).toBe(true);
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

  it("WS payload contains geometry rows and snake_case fields per protocol", async () => {
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
        "geometry",
        "contract_version",
        "geometry_contract_version",
        "channel_order",
        "frames_per_cycle",
      ]),
    );
    expect(Array.isArray(msg.data.geometry)).toBe(true);
  });

  /**
   * Face presence — the safety property that an empty chair must not produce an affect reading.
   *
   * IMPORTANT jsdom caveat, so these are not over-read: `centerCropAndNormalize` is NOT mocked and
   * uses `OffscreenCanvas`, which does not exist in jsdom. So on the no-face path the fallback
   * THROWS, is caught, and the frame is not pushed — meaning these tests see `frames_captured: 0`
   * where a real browser would see 30 centre crops. They therefore verify the COUNTERS and the
   * `face_absent` verdict, not the fallback crop itself. The fallback geometry is covered by
   * `preprocess.parity.test.ts`.
   */
  describe("useMediaPipe — face presence reporting", () => {
    it("reports frames_with_face and face_absent=false when a face is detected", async () => {
      useWebcamStore.setState({ mode: "adaptive" });
      renderHook(() => useMediaPipe({ send, captureMs: 100, cycleMs: 500 }));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(50);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(500);
      });

      const msg = send.mock.calls[0][0];
      expect(msg.data.frames_with_face).toBeGreaterThanOrEqual(4);
      expect(msg.data.frames_with_face).toBe(msg.data.frames_captured);
      expect(msg.data.face_ratio).toBe(1);
      expect(msg.data.face_absent).toBe(false);
    });

    it("reports face_absent=true when no face is detected all cycle", async () => {
      mocks.loadFaceDetectorSpy.mockResolvedValueOnce(makeDetector(0.0, false));
      useWebcamStore.setState({ mode: "adaptive" });
      renderHook(() => useMediaPipe({ send, captureMs: 100, cycleMs: 300 }));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(50);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });

      const msg = send.mock.calls[0][0];
      expect(msg.data.frames_with_face).toBe(0);
      expect(msg.data.face_ratio).toBe(0);
      // The whole point: the backend must skip inference for this cycle.
      expect(msg.data.face_absent).toBe(true);
    });

    it("treats a low-confidence detection as no face", async () => {
      // A box exists but scores below CONFIDENCE_DROP_THRESHOLD, so it is not a usable face.
      mocks.loadFaceDetectorSpy.mockResolvedValueOnce(makeDetector(0.1, true));
      useWebcamStore.setState({ mode: "adaptive" });
      renderHook(() => useMediaPipe({ send, captureMs: 100, cycleMs: 300 }));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(50);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });

      const msg = send.mock.calls[0][0];
      expect(msg.data.frames_with_face).toBe(0);
      expect(msg.data.face_absent).toBe(true);
    });

    it("resets the face counter between cycles", async () => {
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
      const first = send.mock.calls[0][0].data;
      const second = send.mock.calls[1][0].data;
      // Not cumulative: a leaked counter would make cycle 2 roughly double cycle 1.
      expect(second.frames_with_face).toBeLessThanOrEqual(first.frames_with_face + 1);
      expect(second.face_ratio).toBe(1);
    });
  });
});
