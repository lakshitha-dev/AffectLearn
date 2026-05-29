# AffectLearn — Frontend

Next.js 16 + React 19 + Tailwind. Single-page-application frontend for the
adaptive e-learning platform.

## Development

```bash
npm install
npm run dev          # Next.js dev server (Turbopack) on :3000
npm run test         # vitest unit tests
npm run test:e2e     # Playwright end-to-end tests (requires backend on :8000)
npm run build        # production build
```

## Environment

Copy `.env.example` to `.env.local` and adjust as needed. Key variables:

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_URL` | REST API base URL (default `http://localhost:8000/api/v1`). |
| `NEXT_PUBLIC_WS_URL` | WebSocket base URL (default `ws://localhost:8000`). |
| `NEXT_PUBLIC_AFFECT_DEBUG` | Set to `1` to render the affect-detection debug overlay on lesson pages (Story 4.2 AC #11). Shows per-frame latency, captured/dropped frame counts, current cycle number, and the MediaPipe load timestamp. Off by default. |

## Affect-detection pipeline (Story 4.2)

The client captures webcam frames, runs MediaPipe Face Detection in-browser,
preprocesses each face to a 96×96 ImageNet-normalized tensor, and sends the
tensor batch to the server every 30 seconds over the learner WebSocket.

**Privacy invariants:**

- Raw `MediaStream` data never leaves the browser. Only the preprocessed
  `Float32Array` tensor is base64-encoded onto the wire.
- The webcam LED is turned off on lesson-page unmount (all tracks `stop()`ed).
- Nothing facial-related is written to `localStorage`, `sessionStorage`,
  `IndexedDB`, or cookies.

**Preprocessing contract (`src/lib/preprocess.ts`):**

The file `src/lib/preprocess.ts` is the **single source of truth** for the
preprocessing pipeline. Its `PREPROCESS_CONTRACT` constant (crop size,
channel order, dtype, ImageNet mean/std, frame rate) must remain
byte-identical with the ML training repo's `preprocess.py`. Changing any
value here without a coordinated update in the ML repo will silently
corrupt inference accuracy — see the file header for the warning.

**MediaPipe assets (`src/lib/mediapipe-config.ts`):**

The WASM bundle and the `blaze_face_short_range.tflite` model are loaded
from CDN (jsdelivr + Google Cloud Storage) by default. To self-host, copy
both to `public/mediapipe/` and update the two URL constants — no other
code changes required.
