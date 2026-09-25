"use client";

/**
 * useMediaPipe — client-side facial feature capture (Story 4.2).
 *
 * Responsibilities (mapped to AC #3-5, #7-9, #11):
 *   - Mode-gated lifecycle: inert unless `webcamMode === "adaptive"` (AC #3, #7).
 *   - Acquires the webcam stream, lazy-loads MediaPipe, runs face detection at
 *     1 fps (AC #4).
 *   - At each 30s cycle boundary, sends a `facial_features` WS message
 *     containing the concatenated preprocessed frames (AC #5).
 *   - Stream failure (`track.onended`) flips `webcamMode → "error"` (AC #8).
 *   - Backpressure: cycle is dropped (NOT queued) when the WS is disconnected
 *     (AC #9).
 *   - Debug metrics exposed in dev only (AC #11).
 *
 * Privacy invariants enforced here:
 *   - Raw `MediaStream` never leaves the browser. Only the preprocessed
 *     `Float32Array` (96×96×3 per frame) is base64-encoded onto the WS payload.
 *   - On unmount or mode-away, all tracks are `stop()`ed → webcam LED turns off.
 *   - No `localStorage`, `sessionStorage`, `IndexedDB`, or cookie writes.
 *
 * Dependencies (Story 4.1): The lesson page mounts `useWebSocket()` once and
 * passes its `send` function to this hook via `options.send`. We do NOT call
 * `useWebSocket()` here — the architecture mandates a single connection per
 * learner session. `isConnected` is read non-reactively from the connection
 * store at cycle boundary.
 */

import { useEffect, useRef } from "react";

import { useConnectionStore } from "@/stores/connection-store";
import { useWebcamStore } from "@/stores/webcam-store";
import { loadFaceLandmarker } from "@/lib/mediapipe-loader";
import { PREPROCESS_CONTRACT } from "@/lib/preprocess";
import {
  GEOMETRY_CONTRACT,
  frameGeometry,
  geometryToWire,
  toRowMajor,
  type Landmark,
} from "@/lib/geometry";
import type {
  FacialFeaturesMessage,
  WSMessage,
} from "@/types/ws-messages";

const DEFAULT_CAPTURE_MS = 1000;
const DEFAULT_CYCLE_MS = 30_000;
const CONFIDENCE_DROP_THRESHOLD = 0.5;
const CONTRACT_VERSION = 1;
const FRAME_BUDGET_MS = 50; // NFR6

const IS_DEV =
  typeof process !== "undefined" && process.env.NODE_ENV !== "production";

export interface UseMediaPipeOptions {
  /** Send function from the parent's `useWebSocket()` call (Story 4.1). */
  send: (msg: WSMessage) => void;
  /** Force-disable even when mode === "adaptive" (e.g. test harness). */
  enabled?: boolean;
  /** Override the 1000ms capture interval (testing only). */
  captureMs?: number;
  /** Override the 30000ms cycle interval (testing only). */
  cycleMs?: number;
  /**
   * The section the learner is currently on. Sent with each cycle so the server can ground
   * adaptation prompts in the material on screen. Read through a ref internally so that
   * navigating between sections does not tear down and restart the capture loop.
   */
  sectionId?: string;
}

export interface DebugMetrics {
  lastFrameLatencyMs: number;
  meanFrameLatencyMs: number;
  framesCaptured: number;
  droppedFrames: number;
  /** Frames this cycle that contained a real detected face (vs a centre-crop fallback). */
  facesSeen: number;
  mediaPipeLoadedAt: number | null;
  cycleNumber: number;
}

export interface UseMediaPipeReturn {
  /** Live debug ref — populated only in dev. */
  debug: React.RefObject<DebugMetrics | null>;
}

function makeEmptyMetrics(): DebugMetrics {
  return {
    lastFrameLatencyMs: 0,
    meanFrameLatencyMs: 0,
    framesCaptured: 0,
    droppedFrames: 0,
    facesSeen: 0,
    mediaPipeLoadedAt: null,
    cycleNumber: 0,
  };
}

interface DroppedReasons {
  no_face: number;
  low_confidence: number;
}

export function useMediaPipe(options: UseMediaPipeOptions): UseMediaPipeReturn {
  const { send, enabled = true, captureMs, cycleMs, sectionId } = options;
  const mode = useWebcamStore((s) => s.mode);

  // Held in a ref, not a dependency: the capture effect below tears down and rebuilds the
  // MediaPipe pipeline when its deps change, and the learner changes section far more often
  // than a 30s cycle. Reading the latest value at cycle time keeps navigation cheap.
  const sectionIdRef = useRef<string | undefined>(sectionId);
  sectionIdRef.current = sectionId;
  // The section this 30 s window STARTED on. A window is sent when it closes, so labelling it with
  // the section on screen at send time made "bored for 25 s on page A" arrive as a reading about
  // page B, and the hint was written for the wrong page. The server withholds a reading whose
  // section is no longer on screen.
  const windowSectionRef = useRef<string | undefined>(sectionId);

  const debugRef = useRef<DebugMetrics | null>(
    IS_DEV ? makeEmptyMetrics() : null,
  );

  // Stable ref to send so the effect doesn't re-fire if the caller's reference changes.
  const sendRef = useRef(send);
  sendRef.current = send;

  useEffect(() => {
    if (!enabled) return;
    if (mode !== "adaptive") return;
    if (typeof window === "undefined") return; // SSR safety

    // Per-activation refs (closed-over by the interval handlers).
    let cancelled = false;
    let stream: MediaStream | null = null;
    let video: HTMLVideoElement | null = null;
    let captureInterval: ReturnType<typeof setInterval> | null = null;
    let cycleInterval: ReturnType<typeof setInterval> | null = null;
    // Geometry rows, one per captured frame, in GEOMETRY_CHANNEL_ORDER. Replaces the pixel
    // tensor buffer: ~600 bytes per cycle instead of ~4.4 MB, and no image leaves the browser.
    const geometry: number[][] = [];
    // Previous frame's landmarks, for the inter-frame motion channel. Cleared on a frame with no
    // face so motion is never measured across a gap — that would report a jump as fidgeting.
    let prevLandmarks: Landmark[] | null = null;
    const dropped: DroppedReasons = { no_face: 0, low_confidence: 0 };
    // Frames in the current cycle that contained a real detected face.
    //
    // NOT derivable from `frames.length - droppedTotal`: the crop-failure path also increments
    // `low_confidence`, and since faceless frames are now kept as centre crops rather than
    // dropped, `frames.length` no longer means "frames with a face". This counter is what tells
    // the pipeline whether a learner was actually in front of the camera.
    let facesSeen = 0;
    let cycleNumber = 0;
    let cycleStartedAt = 0;
    const latencyHistory: number[] = [];

    if (IS_DEV) debugRef.current = makeEmptyMetrics();

    function resetCycle() {
      geometry.length = 0;
      prevLandmarks = null;
      dropped.no_face = 0;
      dropped.low_confidence = 0;
      facesSeen = 0;
      cycleStartedAt = Date.now();
      latencyHistory.length = 0;
      if (IS_DEV && debugRef.current) {
        debugRef.current.framesCaptured = 0;
        debugRef.current.droppedFrames = 0;
        debugRef.current.facesSeen = 0;
      }
    }

    async function start() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true });
      } catch (err) {
        console.warn("[useMediaPipe] getUserMedia failed", err);
        useWebcamStore.getState().setMode("error");
        return;
      }
      if (cancelled) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }

      stream.getTracks().forEach((t) => {
        t.addEventListener("ended", handleTrackEnded);
      });

      video = document.createElement("video");
      video.muted = true;
      video.playsInline = true;
      video.srcObject = stream;
      try {
        await video.play();
      } catch (err) {
        console.warn("[useMediaPipe] video.play() rejected", err);
      }
      if (cancelled) {
        cleanup();
        return;
      }

      let landmarker;
      try {
        landmarker = await loadFaceLandmarker();
        if (IS_DEV && debugRef.current) {
          debugRef.current.mediaPipeLoadedAt = Date.now();
        }
      } catch (err) {
        console.warn("[useMediaPipe] face landmarker load failed", err);
        useWebcamStore.getState().setMode("error");
        cleanup();
        return;
      }
      if (cancelled) {
        cleanup();
        return;
      }

      cycleNumber = 1;
      resetCycle();

      const onCapture = () => {
        if (!video || !landmarker) return;
        if (video.readyState < 2) return; // HAVE_CURRENT_DATA — first frame not ready yet

        const tStart = performance.now();
        let result;
        try {
          result = landmarker.detectForVideo(video, tStart);
        } catch (err) {
          console.warn("[useMediaPipe] detectForVideo threw", err);
          return;
        }

        const faces = result?.faceLandmarks ?? [];
        // numFaces is 1, so there is at most one. Unlike the pixel path there is no
        // largest-of-several choice to make, and no bystander ambiguity to resolve.
        const pts = faces.length > 0 ? (faces[0] as Landmark[]) : null;
        const matrix = result?.facialTransformationMatrixes?.[0];

        if (pts) {
          facesSeen += 1;
        } else {
          dropped.no_face += 1;
        }

        try {
          // A frame with no face contributes a row of NaN (plus face_found = 0), NOT zeros.
          // Zero is a real gaze reading meaning "looking straight ahead", so recording it here
          // would log attentiveness at exactly the moment the learner looked away.
          const row = frameGeometry(
            pts,
            matrix ? toRowMajor(matrix) : null,
            prevLandmarks,
          );
          if (geometry.length >= GEOMETRY_CONTRACT.framesPerCycle) {
            geometry.shift();
          }
          geometry.push(row);
          prevLandmarks = pts;
        } catch (err) {
          console.warn("[useMediaPipe] geometry failed", err);
          dropped.low_confidence += 1;
          prevLandmarks = null;
        }

        const elapsed = performance.now() - tStart;
        if (elapsed > FRAME_BUDGET_MS) {
          console.warn(
            "[useMediaPipe] frame over budget",
            Math.round(elapsed),
            "ms",
          );
        }
        if (IS_DEV && debugRef.current) {
          latencyHistory.push(elapsed);
          debugRef.current.lastFrameLatencyMs = elapsed;
          debugRef.current.meanFrameLatencyMs =
            latencyHistory.reduce((a, b) => a + b, 0) / latencyHistory.length;
          debugRef.current.framesCaptured = geometry.length;
          debugRef.current.droppedFrames = dropped.no_face + dropped.low_confidence;
          debugRef.current.facesSeen = facesSeen;
        }
      };

      const onCycle = () => {
        const now = Date.now();
        const framesCaptured = geometry.length;
        const droppedTotal = dropped.no_face + dropped.low_confidence;
        // Presence is derived from the RETAINED window, not from a running counter.
        //
        // Capture runs for the whole 30s cycle at 1 fps, but `geometry` is a ring buffer holding
        // the trailing `framesPerCycle` rows -- the window the model is actually scored on, and
        // the length that must match training. `facesSeen` counted every capture, so the ratio was
        // 30/10 and the monitor reported 300% face presence. Reading `face_found` back out of the
        // buffer makes the numerator and denominator describe the same frames by construction.
        const foundIdx = GEOMETRY_CONTRACT.channels.indexOf("face_found");
        const facesInWindow = geometry.reduce((n, row) => n + (row[foundIdx] === 1 ? 1 : 0), 0);
        const faceRatio = framesCaptured === 0 ? 0 : facesInWindow / framesCaptured;
        // An empty chair must not yield an affect reading. Below the floor the server skips
        // inference and records an empty cycle, restoring the behaviour that existed before the
        // centre-crop fallback was added for training parity.
        const faceAbsent =
          framesCaptured === 0 || faceRatio < PREPROCESS_CONTRACT.minFaceFrameRatio;
        const message: FacialFeaturesMessage = {
          type: "facial_features",
          ts: now,
          data: {
            cycle_number: cycleNumber,
            capture_started_at: cycleStartedAt,
            capture_ended_at: now,
            frames_captured: framesCaptured,
            dropped_frames: droppedTotal,
            dropped_reasons: {
              no_face: dropped.no_face,
              low_confidence: dropped.low_confidence,
            },
            frames_with_face: facesInWindow,
            face_ratio: Math.round(faceRatio * 1000) / 1000,
            face_absent: faceAbsent,
            // Geometry, not pixels. NaN is not representable in JSON, so a missing reading
            // travels as null and is decoded back to NaN server-side rather than coerced to 0.
            geometry: geometryToWire(geometry),
            contract_version: CONTRACT_VERSION,
            geometry_contract_version: GEOMETRY_CONTRACT.version,
            channel_order: GEOMETRY_CONTRACT.channels,
            frames_per_cycle: GEOMETRY_CONTRACT.framesPerCycle,
            section_id: windowSectionRef.current ?? sectionIdRef.current,
          },
        };
        // The next window starts now, on whatever section is on screen now.
        windowSectionRef.current = sectionIdRef.current;

        if (!useConnectionStore.getState().isConnected) {
          // AC #9: drop the cycle (NOT queue) — temporal context would be stale on reconnect.
          console.warn(
            "[useMediaPipe] facial_cycle_dropped_no_ws cycle=",
            cycleNumber,
          );
        } else {
          sendRef.current(message);
        }

        if (IS_DEV && debugRef.current) {
          debugRef.current.cycleNumber = cycleNumber;
        }

        cycleNumber += 1;
        resetCycle();
      };

      captureInterval = setInterval(onCapture, captureMs ?? DEFAULT_CAPTURE_MS);
      cycleInterval = setInterval(onCycle, cycleMs ?? DEFAULT_CYCLE_MS);
    }

    function handleTrackEnded() {
      // AC #8: webcam yanked / OS revoked → flip to error mode. Story 3.4's
      // WebcamIndicator + toast pick this up. Tear ourselves down so we stop
      // emitting facial_features.
      console.warn("[useMediaPipe] track ended — switching to error mode");
      useWebcamStore.getState().setMode("error");
      cleanup();
    }

    function cleanup() {
      if (captureInterval) {
        clearInterval(captureInterval);
        captureInterval = null;
      }
      if (cycleInterval) {
        clearInterval(cycleInterval);
        cycleInterval = null;
      }
      if (stream) {
        stream.getTracks().forEach((t) => {
          t.removeEventListener("ended", handleTrackEnded);
          t.stop();
        });
        stream = null;
      }
      if (video) {
        video.srcObject = null;
        video = null;
      }
      // We intentionally do NOT call detector.close() here — the module-level
      // singleton is shared with CalibrationStep and other lessons; closing it
      // on unmount would force a re-download of WASM/model on every lesson
      // navigation. Use disposeFaceDetector() from tests or page-unload only.
      geometry.length = 0;
      dropped.no_face = 0;
      dropped.low_confidence = 0;
      facesSeen = 0;
    }

    void start();

    return () => {
      cancelled = true;
      cleanup();
    };
  }, [enabled, mode, captureMs, cycleMs]);

  return { debug: debugRef };
}
