/**
 * SINGLE SOURCE OF TRUTH for preprocessing.
 *
 * Must match the geometry the DEPLOYED model was trained with.
 *
 * WARNING, learned the hard way: the committed `training/facial/preprocess.py` documents
 * RAW-BBOX cropping, but the artifact actually in production
 * (`cnn_lstm_confusion_anycut.onnx`) was trained by `crops_mp.py` -- a Colab working copy that
 * was never committed -- using 10% box padding, largest-face selection and a centre-crop
 * fallback. Its model card states this; `preprocess.py` contradicts it.
 *
 * Serving raw boxes against those weights made a face fill 100% of the frame where training had
 * it fill ~69%, and because the ResNet18 backbone is FULLY FROZEN the head had no adapted
 * response to the shifted framing: live P(confused) collapsed into a ~0.05 band around 0.5 while
 * the same model spread properly on its own test set (413/1638 predicted positive).
 *
 * The authoritative geometry reference is `affectlearn-ml/evaluation/crop_gap_eval.py::_haar_crop`,
 * which is what `crops_mp.py` replicated. `preprocess.parity.test.ts` pins it.
 *
 * Architecture refs:
 *   - architecture.md line 370 — 96×96 crop locked.
 *   - architecture.md line 444 — MediaPipe output must match CNN-LSTM input expectations.
 *   - architecture.md line 925 — `preprocess.py` shared between training and serving.
 *   - ml-training-guide-daisee.md lines 137-144 — "byte-identical preprocessing" rule
 *     (silent failure mode if drift).
 *
 * Tensor layout is **CHW** (channels-first) to match PyTorch's `(C, H, W)` convention.
 * Length per frame = 3 * 96 * 96 = 27648 floats = 110,592 bytes.
 */

export const PREPROCESS_CONTRACT = {
  cropSize: 96, // pixels (both width and height)
  channels: 3, // RGB
  channelOrder: "RGB" as const, // NOT BGR
  dtype: "float32" as const, // normalized to [0, 1] then ImageNet-normalized
  mean: [0.485, 0.456, 0.406] as const, // ImageNet RGB means
  std: [0.229, 0.224, 0.225] as const, // ImageNet RGB stds
  frameSamplingHz: 1, // 1 frame per second capture
  cycleDurationSeconds: 30, // matches architecture 30s cycle
  expectedFramesPerCycle: 30, // 1 fps × 30s; dropped frames reduce this
  framesPerInferenceWindow: 16, // CNN-LSTM training used 16-frame samples
  // --- crop geometry: these were implicit before, and being implicit is what let them drift ---
  boxPadFraction: 0.1, // 10% of w/h added on EACH side -> 1.44x detection area
  faceSelection: "largest" as const, // by area; NOT detections[0]
  facelessFallback: "center_crop" as const, // keep the frame, do not drop it
} as const;

export type PreprocessContract = typeof PREPROCESS_CONTRACT;

export const FLOATS_PER_FRAME =
  PREPROCESS_CONTRACT.cropSize *
  PREPROCESS_CONTRACT.cropSize *
  PREPROCESS_CONTRACT.channels; // 27648

export interface BoundingBox {
  originX: number;
  originY: number;
  width: number;
  height: number;
}

/**
 * Pure pixel-math normalizer. Takes the RGBA byte array returned by canvas
 * `getImageData(0, 0, 96, 96)` and produces the CHW float32 tensor. Kept
 * pure so unit tests can call it without needing a working canvas in jsdom.
 *
 * For each channel c in [0..2], for each y in [0..95], for each x in [0..95]:
 *   out[c*96*96 + y*96 + x] = (rgba[(y*96 + x)*4 + c] / 255 - mean[c]) / std[c]
 *
 * Alpha is dropped. `getImageData` returns RGBA — indices 0/1/2 are R/G/B.
 */
export function normalizeRgbaToChwFloat32(
  rgba: Uint8ClampedArray | Uint8Array,
): Float32Array {
  const size = PREPROCESS_CONTRACT.cropSize;
  const expectedLen = size * size * 4;
  if (rgba.length !== expectedLen) {
    throw new Error(
      `normalizeRgbaToChwFloat32: expected ${expectedLen} bytes (${size}x${size} RGBA), got ${rgba.length}`,
    );
  }

  const out = new Float32Array(FLOATS_PER_FRAME);
  const { mean, std } = PREPROCESS_CONTRACT;
  const channelStride = size * size;

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const px = (y * size + x) * 4;
      const flat = y * size + x;
      out[0 * channelStride + flat] = (rgba[px + 0] / 255 - mean[0]) / std[0];
      out[1 * channelStride + flat] = (rgba[px + 1] / 255 - mean[1]) / std[1];
      out[2 * channelStride + flat] = (rgba[px + 2] / 255 - mean[2]) / std[2];
    }
  }

  return out;
}

/**
 * Crop a face region from `source` using the MediaPipe-returned bbox, resize to
 * 96×96 via `OffscreenCanvas.drawImage`, then ImageNet-normalize to a CHW float32
 * tensor of length 27648.
 *
 * `source` accepts any `CanvasImageSource` — HTMLVideoElement (the hook's hidden
 * video), ImageBitmap, OffscreenCanvas, etc. The hook passes the video element
 * directly to skip an extra ImageBitmap copy.
 *
 * Throws if `OffscreenCanvas` / `getContext("2d")` is unavailable — caller (the hook)
 * already gates on `mode === "adaptive"` so this only runs in a browser.
 */
export function cropAndNormalize(
  source: CanvasImageSource,
  bbox: BoundingBox,
  frame?: { width: number; height: number },
): Float32Array {
  const size = PREPROCESS_CONTRACT.cropSize;
  const canvas = new OffscreenCanvas(size, size);
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("cropAndNormalize: OffscreenCanvas 2d context unavailable");
  }

  // Frame bounds are needed to clamp the padded box. When the caller does not supply them we
  // clamp only at the origin, which is the best that can be done without knowing the extent.
  const box = padBox(bbox, frame);

  ctx.drawImage(source, box.originX, box.originY, box.width, box.height, 0, 0, size, size);

  const imageData = ctx.getImageData(0, 0, size, size);
  return normalizeRgbaToChwFloat32(imageData.data);
}

/**
 * Expand a detection box by `boxPadFraction` on each side, clamped to the frame.
 *
 * Training padded by 10% per side, so the crop covered 1.44x the detection area and the face
 * occupied ~69% of the 96x96 input. Serving the raw box put the face at ~100% and misregistered
 * every conv filter the frozen backbone relies on.
 */
export function padBox(
  bbox: BoundingBox,
  frame?: { width: number; height: number },
): BoundingBox {
  const pad = PREPROCESS_CONTRACT.boxPadFraction;
  const px = bbox.width * pad;
  const py = bbox.height * pad;

  const x1 = Math.max(0, bbox.originX - px);
  const y1 = Math.max(0, bbox.originY - py);
  const x2raw = bbox.originX + bbox.width + px;
  const y2raw = bbox.originY + bbox.height + py;
  const x2 = frame ? Math.min(frame.width, x2raw) : x2raw;
  const y2 = frame ? Math.min(frame.height, y2raw) : y2raw;

  return { originX: x1, originY: y1, width: Math.max(1, x2 - x1), height: Math.max(1, y2 - y1) };
}

/**
 * The largest-area detection. Training used `max(faces, key=w*h)`; taking `detections[0]` meant
 * a bystander could be picked over the learner.
 */
export function largestBox<T extends BoundingBox>(boxes: readonly T[]): T | undefined {
  if (boxes.length === 0) return undefined;
  return boxes.reduce((best, b) => (b.width * b.height > best.width * best.height ? b : best));
}

/**
 * Centred square covering the frame, as the crop for a frame with no detected face.
 *
 * Training emitted this rather than dropping the frame, so training clips contained occasional
 * non-face frames and the LSTM learned over that distribution. Dropping them here changed the
 * temporal statistics of every served clip.
 */
export function centerCropBox(frame: { width: number; height: number }): BoundingBox {
  const side = Math.min(frame.width, frame.height);
  return {
    originX: Math.floor((frame.width - side) / 2),
    originY: Math.floor((frame.height - side) / 2),
    width: side,
    height: side,
  };
}

/**
 * Centre-crop a frame with no usable detection. Bypasses `padBox` -- the square is already the
 * full extent, so padding it would only re-clamp to the same box.
 */
export function centerCropAndNormalize(
  source: CanvasImageSource,
  frame: { width: number; height: number },
): Float32Array {
  const size = PREPROCESS_CONTRACT.cropSize;
  const canvas = new OffscreenCanvas(size, size);
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("centerCropAndNormalize: OffscreenCanvas 2d context unavailable");
  }
  const b = centerCropBox(frame);
  ctx.drawImage(source, b.originX, b.originY, b.width, b.height, 0, 0, size, size);
  return normalizeRgbaToChwFloat32(ctx.getImageData(0, 0, size, size).data);
}

/**
 * Base64-encode a Float32Array's underlying buffer for WS transport.
 *
 * Uses 32KB chunks to avoid `Maximum call stack size exceeded` from
 * `String.fromCharCode(...veryLargeArray)`. The per-frame payload is 110,592 bytes;
 * a 30-frame cycle is ~3.3 MB pre-base64.
 */
export function toBase64(tensor: Float32Array): string {
  if (tensor.length === 0) return "";

  const bytes = new Uint8Array(
    tensor.buffer,
    tensor.byteOffset,
    tensor.byteLength,
  );
  const CHUNK = 0x8000; // 32KB
  let binary = "";
  for (let i = 0; i < bytes.length; i += CHUNK) {
    const slice = bytes.subarray(i, Math.min(i + CHUNK, bytes.length));
    binary += String.fromCharCode.apply(null, slice as unknown as number[]);
  }
  return btoa(binary);
}

/**
 * Concatenate multiple per-frame CHW float32 tensors into one buffer, then base64.
 * The server reshapes to `(frames, 3, 96, 96)` and picks
 * `framesPerInferenceWindow` of them.
 */
export function framesToBase64(frames: Float32Array[]): string {
  if (frames.length === 0) return "";

  const totalFloats = frames.length * FLOATS_PER_FRAME;
  const merged = new Float32Array(totalFloats);
  for (let i = 0; i < frames.length; i++) {
    merged.set(frames[i], i * FLOATS_PER_FRAME);
  }
  return toBase64(merged);
}
