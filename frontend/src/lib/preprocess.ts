/**
 * SINGLE SOURCE OF TRUTH for preprocessing.
 *
 * Must match `affectlearn-ml/training/facial/preprocess.py` byte-for-byte.
 * Do not modify without a coordinated change in the ML repo.
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
): Float32Array {
  const size = PREPROCESS_CONTRACT.cropSize;
  const canvas = new OffscreenCanvas(size, size);
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("cropAndNormalize: OffscreenCanvas 2d context unavailable");
  }

  ctx.drawImage(
    source,
    bbox.originX,
    bbox.originY,
    bbox.width,
    bbox.height,
    0,
    0,
    size,
    size,
  );

  const imageData = ctx.getImageData(0, 0, size, size);
  return normalizeRgbaToChwFloat32(imageData.data);
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
