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
