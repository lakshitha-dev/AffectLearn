/**
 * MediaPipe asset URLs (Story 4.2 — Task 1.3).
 *
 * Hosting strategy:
 *   - Dev/pilot: CDN-hosted WASM (`cdn.jsdelivr.net`) and TFLite model
 *     (`storage.googleapis.com/mediapipe-models`). Architecture line 232 explicitly
 *     defers "CDN configuration for static assets" to post-MVP.
 *   - To self-host later: copy the WASM bundle + `.tflite` to
 *     `frontend/public/mediapipe/` and change the two constants below to relative
 *     paths (e.g. `"/mediapipe/wasm"`, `"/mediapipe/blaze_face_short_range.tflite"`).
 *     No other code needs to change — the loader (`mediapipe-loader.ts`) and
 *     calibration step both resolve via this module.
 *
 * Privacy note (architecture line 366-373): MediaPipe runs entirely in-browser
 * via WASM. Once the WASM and `.tflite` are downloaded, inference is local —
 * no continuous calls to `*.google.com` at runtime. Verify in DevTools.
 */

export const MEDIAPIPE_WASM_URL =
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/wasm";

export const MEDIAPIPE_FACE_DETECTOR_MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite";

/**
 * FaceLandmarker — 478 landmarks plus the 4x4 facial transformation matrix, which the geometry
 * channel needs and the detector above cannot provide (it returns only a bounding box and six
 * keypoints).
 *
 * This is the SAME model file the training pipeline used
 * (`affectlearn-ml/training/engagenet/face_landmarker.task`, float16 v1). Pinning the version is
 * part of the train/serve contract: a different landmarker revision moves landmark positions
 * slightly, which shifts every derived measurement the model was fitted on.
 */
export const MEDIAPIPE_FACE_LANDMARKER_MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
