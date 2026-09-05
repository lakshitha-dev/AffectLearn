/**
 * MediaPipe FaceDetector loader (Story 4.2 — Task 3).
 *
 * Shared by `useMediaPipe` (lesson page) and `CalibrationStep` (onboarding) so the
 * WASM bundle + `.tflite` model are downloaded once per page session.
 *
 * GPU delegate is requested first; on failure (e.g. WebGL2 unavailable) the loader
 * transparently falls back to CPU. Either path yields a `FaceDetector` configured
 * for `runningMode: "VIDEO"` with `minDetectionConfidence: 0.5` — frames below this
 * are dropped per AC #4.
 */

import { FaceDetector, FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";

import {
  MEDIAPIPE_FACE_DETECTOR_MODEL_URL,
  MEDIAPIPE_FACE_LANDMARKER_MODEL_URL,
  MEDIAPIPE_WASM_URL,
} from "./mediapipe-config";

const DETECTOR_MIN_CONFIDENCE = 0.5;

// `WasmFileset` is declared internally by @mediapipe/tasks-vision and not exported;
// derive it from the resolver's return type instead of importing.
type WasmFilesetT = Awaited<ReturnType<typeof FilesetResolver.forVisionTasks>>;

let detectorPromise: Promise<FaceDetector> | null = null;
let wasmFilesetPromise: Promise<WasmFilesetT> | null = null;

async function getWasmFileset(): Promise<WasmFilesetT> {
  if (!wasmFilesetPromise) {
    wasmFilesetPromise = FilesetResolver.forVisionTasks(MEDIAPIPE_WASM_URL);
  }
  return wasmFilesetPromise;
}

async function createDetectorWithDelegate(
  delegate: "GPU" | "CPU",
): Promise<FaceDetector> {
  const fileset = await getWasmFileset();
  return FaceDetector.createFromOptions(fileset, {
    baseOptions: {
      modelAssetPath: MEDIAPIPE_FACE_DETECTOR_MODEL_URL,
      delegate,
    },
    runningMode: "VIDEO",
    minDetectionConfidence: DETECTOR_MIN_CONFIDENCE,
  });
}

/**
 * Lazily create (or return the cached) `FaceDetector`. Safe to call concurrently
 * — repeated calls during the same load return the same in-flight promise.
 */
export function loadFaceDetector(): Promise<FaceDetector> {
  if (detectorPromise) return detectorPromise;

  detectorPromise = createDetectorWithDelegate("GPU").catch((gpuErr) => {
    console.warn(
      "[mediapipe-loader] GPU delegate unavailable, falling back to CPU",
      gpuErr,
    );
    return createDetectorWithDelegate("CPU");
  });

  // If both attempts fail, clear the cache so the next call retries fresh.
  detectorPromise.catch(() => {
    detectorPromise = null;
    wasmFilesetPromise = null;
  });

  return detectorPromise;
}

let landmarkerPromise: Promise<FaceLandmarker> | null = null;

async function createLandmarkerWithDelegate(
  delegate: "GPU" | "CPU",
): Promise<FaceLandmarker> {
  const fileset = await getWasmFileset();
  return FaceLandmarker.createFromOptions(fileset, {
    baseOptions: {
      modelAssetPath: MEDIAPIPE_FACE_LANDMARKER_MODEL_URL,
      delegate,
    },
    runningMode: "VIDEO",
    numFaces: 1,
    // The geometry channel needs the 4x4 pose matrix; blendshapes are not used and are
    // switched off because they are the expensive half of the graph.
    outputFacialTransformationMatrixes: true,
    outputFaceBlendshapes: false,
  });
}

/**
 * Lazily create (or return the cached) `FaceLandmarker` — 478 landmarks plus the facial
 * transformation matrix, which the geometry channel needs.
 *
 * Same GPU-then-CPU fallback as the detector, and it shares the WASM fileset, so enabling the
 * geometry channel costs one extra model download rather than a second runtime.
 */
export function loadFaceLandmarker(): Promise<FaceLandmarker> {
  if (landmarkerPromise) return landmarkerPromise;

  landmarkerPromise = createLandmarkerWithDelegate("GPU").catch((gpuErr) => {
    console.warn(
      "[mediapipe-loader] GPU delegate unavailable for landmarker, falling back to CPU",
      gpuErr,
    );
    return createLandmarkerWithDelegate("CPU");
  });
  return landmarkerPromise;
}

/** Dispose the cached landmarker. Mirrors `disposeFaceDetector`. */
export async function disposeFaceLandmarker(): Promise<void> {
  if (!landmarkerPromise) return;
  try {
    const lm = await landmarkerPromise;
    lm.close();
  } catch {
    // Load failed or close threw — both fine for cleanup.
  } finally {
    landmarkerPromise = null;
  }
}

/**
 * Dispose the cached detector. Intended for tests and for the hook's cleanup
 * path when the lesson page unmounts.
 */
export async function disposeFaceDetector(): Promise<void> {
  if (!detectorPromise) return;
  try {
    const detector = await detectorPromise;
    detector.close();
  } catch {
    // Either the load failed (already cleared) or close threw — both are fine for cleanup.
  } finally {
    detectorPromise = null;
    wasmFilesetPromise = null;
  }
}

/** Test-only: reset cached singletons without touching a real detector. */
export function __resetForTests(): void {
  detectorPromise = null;
  landmarkerPromise = null;
  wasmFilesetPromise = null;
}
