# Model artifacts

The affect-detection agent loop (Epic 4) loads its ONNX models from this directory at
runtime. Paths resolve relative to the backend working dir and are overridable via env
(see `backend/.env.example` → "Affect / ML pipeline").

| File | Model | Status |
|---|---|---|
| `behavioral_bilstm.onnx` | Behavioral Bi-LSTM (Story 4.4b), input `window (B,30,13)` → `logits (B,4)` | **wired** |
| `behavioral_feature_stats.json` | Global z-score mean/std for the 13 behavioral features | **wired** |
| `cnn_lstm_best.onnx` | Facial CNN-LSTM (Story 4.4), input `clip (B,T,3,96,96)` → `logits (B,4)` | **not exported yet** — drop here to enable |

## Wiring the facial model

The facial CNN-LSTM is trained in `affectlearn-ml/training/facial/` but has not been
exported to ONNX. To light up the facial path (zero backend code change — swappable
artifact, Story 4.4 decision):

1. **Export** from the trained checkpoint:
   ```
   python affectlearn-ml/training/facial/export_onnx.py \
       --checkpoint <path/to/cnn_lstm_best.pt> --out cnn_lstm_best.onnx
   ```
2. **Copy** `cnn_lstm_best.onnx` into this directory.
3. **Set the kind** via `AFFECT_MODEL_KIND`:
   - `engagement` — current stand-in (model emits 4 DAiSEE engagement levels; mapped to
     `engaged`/`bored` via the temporary adapter).
   - `category` — true 4-class model (`bored`/`confused`/`engaged`/`frustrated`), mapped
     index→label directly.

Until the facial ONNX is present, the facial path returns `model_unavailable` and the
pipeline runs behavioral-only (and multimodal fusion degrades to behavioral).
