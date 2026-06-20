# Model artifacts

The affect-detection agent loop (Epic 4) loads its ONNX models from this directory at
runtime. Paths resolve relative to the backend working dir and are overridable via env
(see `backend/.env.example` → "Affect / ML pipeline").

| File | Model | Status |
|---|---|---|
| `behavioral_bilstm.onnx` | Behavioral Bi-LSTM (Story 4.4b), input `window (B,30,13)` → `logits (B,4)` | **wired** |
| `behavioral_feature_stats.json` | Global z-score mean/std for the 13 behavioral features | **wired** |
| `cnn_lstm_best.onnx` | Facial CNN-LSTM (Story 4.4), input `clip (B,T,3,96,96)` → `logits (B,4)` | **wired** (engagement stand-in) — **gitignored** (46MB), fetch from Drive |

## Facial model — fetch & wiring

`cnn_lstm_best.onnx` is **46MB** so it is **gitignored** (only the small behavioral ONNX is
committed). Fetch it before running the affect pipeline locally:

1. **Copy** from Google Drive:
   `G:/My Drive/affectlearn-ml/models/cnn_lstm_best.onnx`  →  this directory.
   (Or re-export: `python affectlearn-ml/training/facial/export_onnx.py
   --checkpoint <cnn_lstm_best.pt> --out cnn_lstm_best.onnx`.)
2. No code change needed — `AFFECT_MODEL_PATH` defaults to `models/cnn_lstm_best.onnx`.
   Loading is lazy; the next cycle picks it up (no restart required).

### Status / caveats
- **This is the ENGAGEMENT stand-in**, not a 4-category model. DAiSEE facial training is
  single-affect (`target_affect: Engagement`, 4 *intensity* levels), so `AFFECT_MODEL_KIND`
  is `engagement` (default). In fusion the face contributes **only `bored`/`engaged`** mass;
  `confused`/`frustrated` come from the behavioral Bi-LSTM. Fusion is fully operational.
- A **true 4-category** facial model (`AFFECT_MODEL_KIND=category`) does **not exist yet**.
  The per-affect binaries on Drive (`cnn_lstm_{boredom,confusion,frustration}.pt`) are
  **weak** — a real webcam session showed frustration collapses to one class (~85%
  "very_low") and confusion is ≈chance — so they are intentionally NOT wired. Revisit after
  real pilot data (measure if it actually helps the fusion ablation).
- `cnn_lstm_balanced_f1509.onnx` (reported wF1 0.509 "best") is **broken on Drive** — exported
  with a missing external-data sidecar (`.onnx.data`). Re-export self-contained if needed;
  `cnn_lstm_best.onnx` is the working artifact.

If the facial ONNX is absent, the facial path returns `model_unavailable` and the pipeline
runs behavioral-only (fusion degrades to behavioral) — never crashes.
