/**
 * Per-frame facial geometry — the BROWSER half of a three-file contract.
 *
 * The other two are:
 *   affectlearn-ml/training/engagenet/extract_geometry.py   computed these at training time
 *   backend/app/services/geometry_inference.py              aggregates and scores them
 *
 * Every function here must reproduce its Python counterpart. A divergence is silent: the model
 * keeps returning confident probabilities from features it was never trained on. This project has
 * already paid for that once — the pixel path trained at 1.93 s frame spacing while serving at
 * 0.67 s, with nothing comparing the two. `backend/tests/services/test_geometry_parity.py` holds
 * golden vectors frozen from the Python extractor; change anything here and run it.
 *
 * WHY GEOMETRY INSTEAD OF PIXELS
 *
 * Eleven numbers per frame, ~600 bytes per 30 s cycle, against ~4.4 MB of base64 face crops. No
 * image leaves the browser at all, which is a stronger guarantee than transport encryption can
 * give and is what makes the consent copy accurate.
 *
 * MISSING FACES ARE NaN, NEVER ZERO
 *
 * Zero is a meaningful gaze reading — it means looking straight ahead. A frame with no detected
 * face must therefore contribute NaN so the aggregation excludes it. Recording it as zero would
 * log "attentive" at exactly the moment the learner looked away, inverting the signal the model
 * exists to detect. `face_found` carries the presence flag separately.
 */

/** Channel order. MUST equal GEOMETRY_CHANNEL_ORDER in geometry_inference.py. */
export const GEOMETRY_CHANNEL_ORDER = [
  "yaw",
  "pitch",
  "roll",
  "ear_l",
  "ear_r",
  "ear_mean",
  "mouth_open",
  "gaze_x",
  "gaze_y",
  "motion",
  "face_found",
] as const;

export const GEOMETRY_CONTRACT = {
  version: 1,
  channels: GEOMETRY_CHANNEL_ORDER,
  nChannels: GEOMETRY_CHANNEL_ORDER.length, // 11
  /** 10 frames at 1 fps. A parity term with training, not a tuning choice. */
  framesPerCycle: 10,
  captureFps: 1.0,
} as const;

// MediaPipe FaceLandmarker canonical indices — identical to the Python extractor's constants.
const EYE_L = [33, 160, 158, 133, 153, 144] as const; // outer, upper x2, inner, lower x2
const EYE_R = [362, 385, 387, 263, 373, 380] as const;
const IRIS_L = 468;
const IRIS_R = 473;
const LIP_UP = 13;
const LIP_DN = 14;
const LIP_L = 61;
const LIP_R = 291;

export type Landmark = { x: number; y: number; z: number };

const RAD_TO_DEG = 180 / Math.PI;

/**
 * Yaw/pitch/roll in degrees from the rotation block of a 4x4 facial transformation matrix.
 *
 * Takes the matrix ROW-MAJOR, matching what the Python side reads after reshaping to (4,4).
 * `toRowMajor` below converts MediaPipe's own layout into it.
 *
 * A transposed matrix here swaps yaw and pitch and mirrors roll. That still yields plausible-
 * looking angles in a plausible range, so nothing downstream would flag it — only a parity check
 * against the training pipeline catches it.
 */
export function eulerFromMatrix(m: number[] | Float32Array): [number, number, number] {
  const r = (i: number, j: number) => m[i * 4 + j];
  const sy = Math.sqrt(r(0, 0) * r(0, 0) + r(1, 0) * r(1, 0));
  let pitch: number;
  let yaw: number;
  let roll: number;
  if (sy > 1e-6) {
    pitch = Math.atan2(r(2, 1), r(2, 2));
    yaw = Math.atan2(-r(2, 0), sy);
    roll = Math.atan2(r(1, 0), r(0, 0));
  } else {
    // Gimbal lock: roll is unrecoverable, so pin it rather than emit a noisy value.
    pitch = Math.atan2(-r(1, 2), r(1, 1));
    yaw = Math.atan2(-r(2, 0), sy);
    roll = 0;
  }
  return [yaw * RAD_TO_DEG, pitch * RAD_TO_DEG, roll * RAD_TO_DEG];
}

/**
 * MediaPipe's `Matrix` -> row-major flat, the layout `eulerFromMatrix` expects.
 *
 * UNVERIFIED IN A BROWSER. MediaPipe Tasks returns `{ rows, columns, data }`, and its 4x4
 * transformation matrices follow the OpenGL convention, which is COLUMN-major — so this
 * transposes. That is taken from the format's convention rather than from a live reading, and it
 * is the one term in this file that a unit test cannot settle, because it depends on what the
 * runtime actually hands back rather than on arithmetic.
 *
 * How to check it in one minute: open the lesson page, look at a logged `yaw` while turning your
 * head left and right. Yaw should swing and pitch should stay near flat. If pitch swings instead,
 * the layout is row-major and `transpose` below should be false.
 */
export function toRowMajor(
  matrix: { data: number[] | Float32Array } | number[] | Float32Array,
  transpose = true,
): number[] {
  const data = Array.isArray(matrix) || ArrayBuffer.isView(matrix)
    ? Array.from(matrix as ArrayLike<number>)
    : Array.from((matrix as { data: ArrayLike<number> }).data);
  if (!transpose) return data;
  const out = new Array<number>(16);
  for (let i = 0; i < 4; i += 1) {
    for (let j = 0; j < 4; j += 1) out[i * 4 + j] = data[j * 4 + i];
  }
  return out;
}

function dist2(a: Landmark, b: Landmark): number {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.hypot(dx, dy);
}

function dist3(a: Landmark, b: Landmark): number {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  const dz = a.z - b.z;
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

/** Eye aspect ratio: mean lid separation over eye width. NaN when the eye is degenerate. */
export function eyeAspectRatio(pts: Landmark[], idx: readonly number[]): number {
  const p = idx.map((i) => pts[i]);
  const horiz = dist3(p[0], p[3]);
  if (!(horiz > 1e-8)) return NaN;
  return (dist3(p[1], p[5]) + dist3(p[2], p[4])) / (2 * horiz);
}

/**
 * Iris-centre offset from the eye-corner midpoint, normalised by eye width, averaged over eyes.
 *
 * A proxy, not calibrated gaze: it says how far the irises sit from centre, not where on the
 * screen someone is looking. That is enough for the construct and needs no per-user calibration,
 * which matters for a system that meets each learner once.
 */
export function gazeProxy(pts: Landmark[]): [number, number] {
  if (pts.length <= Math.max(IRIS_L, IRIS_R)) return [NaN, NaN];
  let sx = 0;
  let sy = 0;
  for (const [iris, eye] of [
    [IRIS_L, EYE_L],
    [IRIS_R, EYE_R],
  ] as const) {
    const outer = pts[eye[0]];
    const inner = pts[eye[3]];
    const w = dist3(outer, inner);
    if (!(w > 1e-8)) return [NaN, NaN];
    sx += (pts[iris].x - (outer.x + inner.x) / 2) / w;
    sy += (pts[iris].y - (outer.y + inner.y) / 2) / w;
  }
  return [sx / 2, sy / 2];
}

/** Lip separation over mouth width — scale-free, so camera distance does not enter. */
export function mouthOpenness(pts: Landmark[]): number {
  const w = dist3(pts[LIP_L], pts[LIP_R]);
  if (!(w > 1e-8)) return NaN;
  return dist3(pts[LIP_UP], pts[LIP_DN]) / w;
}

/** Mean 2-D landmark displacement against the previous frame — a fidgeting proxy. */
export function motionEnergy(pts: Landmark[], prev: Landmark[] | null): number {
  if (!prev || prev.length !== pts.length) return NaN;
  let total = 0;
  for (let i = 0; i < pts.length; i += 1) total += dist2(pts[i], prev[i]);
  return total / pts.length;
}

/** One frame's 11 scalars, in GEOMETRY_CHANNEL_ORDER. All NaN except face_found when no face. */
export function frameGeometry(
  pts: Landmark[] | null,
  matrix: number[] | Float32Array | null,
  prev: Landmark[] | null,
): number[] {
  if (!pts || pts.length === 0) {
    const row = new Array<number>(GEOMETRY_CHANNEL_ORDER.length).fill(NaN);
    row[GEOMETRY_CHANNEL_ORDER.indexOf("face_found")] = 0;
    return row;
  }
  const [yaw, pitch, roll] = matrix ? eulerFromMatrix(matrix) : [NaN, NaN, NaN];
  const earL = eyeAspectRatio(pts, EYE_L);
  const earR = eyeAspectRatio(pts, EYE_R);
  // nanmean of the pair: Python averages whichever eyes are measurable.
  const earPair = [earL, earR].filter((v) => Number.isFinite(v));
  const earMean = earPair.length ? earPair.reduce((a, b) => a + b, 0) / earPair.length : NaN;
  const [gazeX, gazeY] = gazeProxy(pts);
  return [
    yaw,
    pitch,
    roll,
    earL,
    earR,
    earMean,
    mouthOpenness(pts),
    gazeX,
    gazeY,
    motionEnergy(pts, prev),
    1,
  ];
}

/**
 * Serialise a cycle for the wire. NaN is not representable in JSON — `JSON.stringify` turns it
 * into `null` — so it is emitted as null explicitly and decoded back to NaN server-side, rather
 * than left to a coercion that would silently become 0 and invert the signal.
 */
export function geometryToWire(frames: number[][]): (number | null)[][] {
  return frames.map((row) => row.map((v) => (Number.isFinite(v) ? v : null)));
}
