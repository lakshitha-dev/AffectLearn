# Method — Collecting Behavioral Data, Training the Behavior Model, and Detecting Real Learners' Feelings (Phase A)

*Status: platform live and verified ready (Azure CLI + live endpoints + a real-participant smoke test). Scope: Phase A only (non-adaptive), 20–30 participants. This is the operating method; it needs no new code — the deployed `main` app already supports the whole flow.*

Companion documents (read alongside — this doc links, does not duplicate):
- **`deploy/azure/PHASE_A_RUN_CHECKLIST.md`** — the step-by-step operational checklist + admin API commands.
- **`deploy/azure/AFFECT_SECTION_CODEBOOK.md`** — which course section is designed to elicit which feeling.
- **`docs/behavioral-data-elicitation-research.md`** — the research rationale (why each state is elicited this way).
- **`docs/references.md`** — the citations.

---

## 1. Is it possible? (the short answer)

| Goal | Possible? | Notes |
|---|---|---|
| **Collect** behavioral data from real learners | **Yes** | Every 30 s the platform saves a `(30×13)` aggregate feature window + the learner's self-report label. Verified live. |
| **Train** the behavioral Bi-LSTM on it | **Yes** | The real-data training path is built and proven end-to-end. 20–30 participants ≈ 1,200–5,000 windows — enough for the small model with class weighting. |
| **Detect** real users' feelings | **Yes, with honest limits** | After retraining, the model runs live every 30 s per learner. Expected accuracy **~50–65%** (behavioral-only literature ceiling), person-dependent — a legitimate result, not a guaranteed high number. Fusion with the face model can lift it. |

**Verified on the deployed `main` app (2026-07):** both App Services `Running`; WebSockets + AlwaysOn `True`; `REDIS_URL` / `DATABASE_URL` / `BEHAVIORAL_MODEL_PATH` set; Redis buffer `Running`; `GET /health/pipeline` = `{"status":"ok","redis":true,"postgres":true,"worker":{"running":true}}`.

---

## 2. How it works (the data path)

1. While a learner studies, the browser captures mouse / keyboard / scroll activity and, every **30 seconds**, sends a summarised window to the server.
2. The server turns it into **13 aggregate features** (mouse entropy, velocities, click count, idle %, hover dwell, keystroke count, typing rhythm, backspace %, pause count, scroll velocity, scroll direction changes, section dwell) across 30 one-second bins → a `(30, 13)` window.
3. That window is **saved** as a research event (`behavioral_affect_detected`, with the `features` array), and the **self-report** the learner gives (~every 2 sections) is saved as the **ground-truth label**.
4. A background worker durably writes everything to PostgreSQL (buffered through Redis).

The self-reports are the "correct answers"; the feature windows are the model's inputs. Training pairs each window with the nearest self-report label.

---

## 3. How the research shapes the run (the "why")

- **Labels come from self-reports** every ~2 sections, with **~20% of prompts randomly omitted** to measure the prompt's own effect (reactivity/Hawthorne control).
- **Course content is designed to bring out each state** (see codebook): **bored** = monotony/low-stimulation text (Pekrun's Control-Value Theory); **confused** = a genuine, resolvable contradiction (D'Mello & Graesser; Lehman et al.); **frustrated** = a hard, gated quiz; **engaged** = clear, well-scaffolded flow.
- **A neutral warm-up course is done first** to record each learner's personal **baseline** — signals are then normalised per person, because individual differences dominate raw mouse/keystroke behaviour.
- **Within-subject design:** every learner passes through all four states, so each learner is their own control.
- **Bias controls:** neutral framing ("a course we're studying"), fixed section order with serial position recorded as a covariate, and the 20% prompt omission above.

---

## 4. The method — step by step

### Stage 1 — Before any participant (pre-flight)
- ✅ **Ethics / IRB approval** — the hard gate. Do not enrol anyone before this.
- Confirm the platform: `GET /health/pipeline` = `ok`; courses seeded (49 sections incl. the warm-up); consent + debrief live; global phase = `phase_a`.
- Recruit 20–30 learners; schedule ~60–90 min sessions.
- Work through `PHASE_A_RUN_CHECKLIST.md`.

### Stage 2 — Per participant (collection)
1. Register → verify email → **assign A/B group** (`POST /api/v1/admin/study/groups`) and record it (used only later, for Phase B).
2. Consent → webcam **Allow** (face + behaviour) **or Deny** (behaviour-only — still valid, and the most important data for this model).
3. **Warm-up course first** (baseline), then the 3 study courses.
4. Data captures itself: behaviour windows every 30 s, self-reports every ~2 sections (20% omitted), gated quizzes with answer timing.
5. When enrolment is complete: **lock groups** (`POST /api/v1/admin/study/groups/lock`).

### Stage 3 — During the pilot (monitoring)
- Check `GET /health/pipeline` daily (must be `ok`). If `degraded`: check the Redis container, then `az webapp restart -g affectlearn-rg -n affectlearn-api-4905`.
- **Mid-pilot label-balance check (the #1 risk):** export the self-reports and look at the class balance. If ≳80% are "engaged," intervene now (re-brief participants, verify the widget) — don't wait until the end.
- Track that each participant produced windows/labels across all four states.

### Stage 4 — Train the behavioural model (after collection)
1. **Export:** `GET /api/v1/admin/research/phase-a-dataset` → save as `affectlearn-ml/data/phase_a/export.json`.
2. **Clean:** run `training/behavioral/data_quality.py` — drop degenerate (single-class) participants and sessions < 15 min.
3. **Configure** `training/behavioral/config.yaml`: `use_synthetic: false`, set `phase_a_export`, keep `label_propagate_ms: 0` (clean, self-reports only) — raise to `120000` (±2 min) only if there are too few labeled windows.
4. **Train in Colab** (`train_bilstm.py`): splits **by participant**, class-weighted, global z-score → exports `behavioral_bilstm.onnx` + `behavioral_feature_stats.json`.
5. **Evaluate:** per-class F1, **per-participant** accuracy, confusion matrix (target ~50–65%).
6. **Deploy:** copy the two artifacts into `backend/models/`, redeploy → the live model is now trained on **real** data.

### Stage 5 — Detect real learners' feelings
- The trained Bi-LSTM runs live every 30 s per learner → feeling + confidence; behaviour-only without a webcam, **fused** with the face model when the webcam is on.
- Live on the admin **Pipeline Monitor**; every detection is stored.
- **Validate (your RQ1/RQ2 result):** compare the model's output against held-out self-reports (accuracy / macro-F1 / confusion), reported per participant.

---

## 5. Dry-run acceptance (do this once before real participants)
1. `GET /health/pipeline` returns `ok`.
2. Run one internal test session yourself (register → warm-up → a study course → give self-reports).
3. Export `phase-a-dataset`, run `train_bilstm.py` on that tiny set to confirm the loop produces an ONNX, then delete the test participant's data.
4. This mirrors the already-passed live smoke test, so it confirms readiness with no risk to the real dataset.

---

## 6. Honest limitations (state these to your supervisor)
- **Small N** → behavioural-only accuracy ~50–65%, person-dependent. The mouse/keystroke signals are **priors to validate**, not proven facts (cite the review caveat in `references.md`).
- **Class imbalance** (engaged dominates) → class weighting is on; report minority-class coverage explicitly.
- **Detection accuracy is unvalidated until the real retrain** — the currently-shipped model is synthetic; real-user accuracy comes only after Stage 4.
- **Fusion is a live confidence-weighted formula**, not a trained model; a real "fusion beats one modality" result (RQ2) needs the paired pilot data.
- **Neutral (warm-up) windows are baseline-only** — they carry no training label by design.
