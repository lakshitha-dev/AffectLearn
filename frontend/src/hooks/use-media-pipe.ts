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
import { loadFaceDetector } from "@/lib/mediapipe-loader";
import {
  centerCropAndNormalize,
  cropAndNormalize,
  largestBox,
  framesToBase64,
  PREPROCESS_CONTRACT,
  type BoundingBox,
} from "@/lib/preprocess";
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
    const frames: Float32Array[] = [];
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
      frames.length = 0;
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

      let detector;
      try {
        detector = await loadFaceDetector();
        if (IS_DEV && debugRef.current) {
          debugRef.current.mediaPipeLoadedAt = Date.now();
        }
      } catch (err) {
        console.warn("[useMediaPipe] face detector load failed", err);
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
        if (!video || !detector) return;
        if (video.readyState < 2) return; // HAVE_CURRENT_DATA — first frame not ready yet

        const tStart = performance.now();
        let result;
        try {
          result = detector.detectForVideo(video, tStart);
        } catch (err) {
          console.warn("[useMediaPipe] detectForVideo threw", err);
          return;
        }

        const detections = result?.detections ?? [];
        const frameDims = { width: video.videoWidth, height: video.videoHeight };

        // Training selected the LARGEST detection, not the first one returned. With a bystander
        // in shot, detections[0] could be the wrong face entirely.
        const usable = detections.filter((d) => {
          const sc = d?.categories?.[0]?.score ?? 0;
          return Boolean(d?.boundingBox) && sc >= CONFIDENCE_DROP_THRESHOLD;
        });
        const chosen = largestBox(
          usable.map((d) => d.boundingBox as BoundingBox),
        );

        // These now count FALLBACKS rather than discarded frames -- the frame is still kept,
        // as a centre crop. `facesSeen` is the separate, honest count of frames that actually
        // contained a face, and is what decides whether this cycle describes a learner at all.
        if (chosen) {
          facesSeen += 1;
        } else if (detections.length === 0) {
          dropped.no_face += 1;
        } else {
          dropped.low_confidence += 1;
        }

        try {
          // Training emitted a centre crop for faceless frames rather than dropping them, so
          // clips contained occasional non-face frames and the LSTM was fitted over that
          // distribution. Dropping them changed the temporal statistics of every served clip.
          const tensor = chosen
            ? cropAndNormalize(video, chosen, frameDims)
            : centerCropAndNormalize(video, frameDims);
          // Enforce ring-buffer bound: never exceed expectedFramesPerCycle frames
          // between cycle resets. Drops the oldest frame (shift) if timers drift.
          if (frames.length >= PREPROCESS_CONTRACT.expectedFramesPerCycle) {
            frames.shift();
          }
          frames.push(tensor);
        } catch (err) {
          console.warn("[useMediaPipe] crop failed", err);
          dropped.low_confidence += 1;
        }

        const elapsed = performance.now() - tStart;
        if (elapsed > FRAME_BUDGET_MS) {
          console.warn(
            `[useMediaPipe] frame ${elapsed.toFixed(1)}ms > ${FRAME_BUDGET_MS}ms budget (NFR6)`,
          );
        }
        latencyHistory.push(elapsed);
        if (latencyHistory.length > PREPROCESS_CONTRACT.expectedFramesPerCycle) {
          latencyHistory.shift();
        }

        if (IS_DEV && debugRef.current) {
          debugRef.current.lastFrameLatencyMs = elapsed;
          debugRef.current.meanFrameLatencyMs =
            latencyHistory.reduce((a, b) => a + b, 0) / latencyHistory.length;
          debugRef.current.framesCaptured = frames.length;
          debugRef.current.droppedFrames = dropped.no_face + dropped.low_confidence;
          debugRef.current.facesSeen = facesSeen;
        }
      };

      const onCycle = () => {
        const now = Date.now();
        const framesCaptured = frames.length;
        const droppedTotal = dropped.no_face + dropped.low_confidence;
        const faceRatio = framesCaptured === 0 ? 0 : facesSeen / framesCaptured;
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
            frames_with_face: facesSeen,
            face_ratio: Math.round(faceRatio * 1000) / 1000,
            face_absent: faceAbsent,
            frames_b64: framesCaptured === 0 ? "" : framesToBase64(frames),
            contract_version: CONTRACT_VERSION,
            crop_size: PREPROCESS_CONTRACT.cropSize,
            channel_order: PREPROCESS_CONTRACT.channelOrder,
            dtype: PREPROCESS_CONTRACT.dtype,
            section_id: sectionIdRef.current,
          },
        };

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
      frames.length = 0;
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
