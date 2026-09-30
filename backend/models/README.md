# Model artifacts

The affect-detection agent loop (Epic 4) loads its ONNX models from this directory at
runtime. Paths resolve relative to the backend working dir and are overridable via env
(see `backend/.env.example` → "Affect / ML pipeline").

**Check what is actually loaded with `GET /health/pipeline` → `models`.** It reports the configured
path, whether the file exists, the *resolved* kind, and the ONNX input/output shapes. That endpoint
exists because the dangerous failure here is silent: `AFFECT_MODEL_KIND=binary_confusion` pointing at
the old 4-level engagement artifact produces confident nonsense rather than an error.

## Current artifacts

| File | Model | Status |
|---|---|---|
| `behavioral_confusion_gbdt.onnx` | Behavioural confusion GBDT. `features (B,80)` → `probabilities (B,2)` | **wired** — committed (53 KB) |
| `behavioral_confusion_gbdt.json` | Provenance + honest metrics card for the above | committed |
| `behavioral_confusion_gbdt_platform.onnx` | The same GBDT refitted on DUX rebuilt as platform-like input (100 ms pointer, one click per press). Same `features (B,80)` contract | **not wired**: select with `BEHAVIORAL_MODEL_PATH`; parity test `tests/services/test_platform_gbdt_parity.py` |
| `behavioral_confusion_gbdt_platform.json` | Its card: LOSO AUC 0.703 [0.675, 0.731] on platform-like DUX; gate sweep; no floor meets the pre-specified 2x-lift rule | committed |
| `cnn_lstm_confusion_anycut.onnx` | Facial confusion CNN-LSTM. `clip (B,16,3,96,96)` → `logits (B,2)` | **wired** — **gitignored** (48 MB), fetched from Blob at deploy |
| `behavioral_bilstm.onnx` | Behavioural Bi-LSTM. `window (B,30,16)` → `logits (B,4)` | **rollback only** — see warning below |
| `behavioral_feature_stats.json` | z-score mean/std for the 16 behavioural features | used by the Bi-LSTM path only |
| `cnn_lstm_best.onnx` | Facial engagement stand-in. `clip (B,16,3,96,96)` → `logits (B,4)` | **rollback only** — gitignored (48 MB) |

## What these models do and do not detect

Both wired models are **binary confusion** detectors. Held out:

| Channel | Artifact | AUC | κ | Protocol |
|---|---|---|---|---|
| Behavioural | `behavioral_confusion_gbdt.onnx` | **0.747** | 0.274 | 46 participants, leave-one-participant-out, permutation *p* = 0.0005 |
| Facial | `cnn_lstm_confusion_anycut.onnx` | **0.641** | 0.212 | DAiSEE test split, n = 1638 |

Confusion is the **only** one of the four target states detectable in the available data. Measured
under an identical pipeline: frustration reads at chance (facial AUC 0.590; behavioural Anger-proxy
recall 0.00), boredom at chance (facial 0.561) and is absent from the DUX annotation scheme entirely,
and DAiSEE contains **4 disengaged clips in 1638** so engagement is unlearnable there.

Consequently `bored` and `frustrated` are pinned at exactly `0.0` in both adapters, and `engaged`
carries `1 − P(confused)` — it is the **absence of detected confusion**, not a detection of
engagement. `ADAPT_STATES=confused` matches that reality; listing states the models cannot see would
let the gate fire on evidence that does not exist.

## ⚠️ `behavioral_bilstm.onnx` was trained on synthetic data

It was exported from a checkpoint stamped `trained_on: "synthetic"`, `reportable: false` — **600
fabricated windows from 15 fabricated participants**. While it was the served model, every
behavioural affect decision the platform made came from a model that had never seen a human. It is
kept only as a rollback target for the *shape* contract; do not treat its output as meaningful.

## Facial model — fetch & wiring

48 MB artifacts are gitignored. `.github/workflows/deploy.yml` fetches them from Blob storage by
read-SAS URL during the backend deploy (`FACIAL_MODEL_URL`, `FACIAL_CONFUSION_MODEL_URL`).

Locally, copy from Drive (`MyDrive/affectlearn-ml/models/`) into this directory, or re-export with
`affectlearn-ml/training/facial/` tooling. Loading is lazy — the next cycle picks up a new file, no
restart needed.

### A correction worth keeping

An earlier version of this file said the per-affect facial binaries were "intentionally NOT wired"
because "confusion is ≈chance". **That judgement was correct** for the checkpoint it referred to:
`cnn_lstm_confusion.pt` stopped at epoch 2 and measures **AUC 0.589** on the test split — chance,
as claimed. `cnn_lstm_confusion_anycut.onnx` is a different model: retrained on the **ANY cut**
(`{1,2,3}` vs `{0}`, 31% positive) rather than the near-unlearnable HIGH cut (8.8% positive), which
took it to 0.641. So the caution was right and the retrain addressed its cause.

The related caution still stands: **facial is the weaker channel** (0.641 vs 0.747), and unfreezing
`layer4` made it *worse* (0.5735) by overfitting 12M parameters to 4,852 clips — the frozen backbone
is deliberate and evidence-backed.

## Degradation and rollback

If the facial ONNX is absent the facial path returns `model_unavailable` and the pipeline runs
behavioural-only — it never crashes. Since behavioural is the stronger channel, that degradation is
mild.

Rollback is **env-only**, no redeploy (loading is lazy):

```
AFFECT_MODEL_PATH=models/cnn_lstm_best.onnx
AFFECT_MODEL_KIND=engagement
BEHAVIORAL_MODEL_PATH=models/behavioral_bilstm.onnx
```

Note that reverting the behavioural path restores the synthetic model — prefer leaving the GBDT in
place and setting `AFFECT_DETECTION_MODE=behavioral_only` if the facial channel is the problem.
