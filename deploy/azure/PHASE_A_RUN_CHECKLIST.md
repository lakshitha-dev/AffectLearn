# Phase A Pilot — Run Checklist

Operating checklist for running Phase A (the **non-adaptive** data-collection phase: the
platform captures behavioral signals + self-report labels and triggers **no** adaptations).
Its output is the training set for the behavioral Bi-LSTM (see
`_bmad-output/planning-artifacts/ml-training-guide-behavioral.md`).

Prod: frontend `https://affectlearn.tech` · backend `affectlearn-api-2026` ·
Postgres `affectlearn-pg-2026` · Redis ACI `affectlearn-redis-aci` · rg `affectlearn-rg`.
All admin routes are under `/api/v1/admin/...` and require an admin account.

---

## 0. One-time pre-flight (before ANY participant)
- [ ] **Ethics / IRB approval** obtained (the hard gate — do not enrol without it).
- [ ] Latest code on `main`, CI + Deploy green.
- [ ] Courses seeded: **4 courses / 49 sections incl the warm-up** ("Getting Comfortable"). Re-seed if needed:
      `DATABASE_URL=<prod> python -m app.db.seed_courses --reset` (prod URL is in the App Service appsettings, not local `.env`).
- [ ] Consent + end-of-study debrief copy live (onboarding + Thank-You screen).
- [ ] **Pipeline liveness = ok**: `GET https://affectlearn-api-2026.azurewebsites.net/health/pipeline`
      → `{"status":"ok","redis":true,"postgres":true,"worker":{"running":true,...}}`.
- [ ] Behavioral model present (`backend/models/behavioral_bilstm.onnx`) so behavioral-only detection works. Facial model optional.
- [ ] Global phase = **phase_a**: `GET /api/v1/admin/study/phase` (default is phase_a).
- [ ] Decide the A/B split (`control` vs `adaptive`). Adaptations are OFF in Phase A regardless; the group is only *recorded* now, used in Phase B.

## 1. Per participant — onboarding
- [ ] Participant registers + verifies email.
- [ ] **Assign A/B group**: `POST /api/v1/admin/study/groups {user_id, group}`. Record it.
- [ ] Complete the **consent** screen (webcam + behavioral tracking + right to withdraw).
- [ ] Webcam: **Allow** (facial + behavioral) OR **Deny** (behavioral-only — still valid, and the most important data for the behavioral model).
- [ ] Participant completes the **warm-up course FIRST** ("Getting Comfortable") — the per-person baseline task.
- [ ] Then the 3 study courses (Foundations → Building → Multi-Agent).

## 2. When enrolment is complete → "pilot begins"
- [ ] **Lock group assignments**: `POST /api/v1/admin/study/groups/lock` (re-assignment after this returns 409 GROUP_LOCKED — prevents accidental mid-study changes).

## 3. During sessions
- [ ] Affect WS loop connected (behavioral windows streaming; dev overlay / backend logs).
- [ ] Self-report prompts appear (~every 2 section completions; **~20% are randomly omitted by design** — expected).
- [ ] Encourage sessions ≥ 15 min (shorter sessions are dropped in cleaning).

## 4. Monitoring (daily + explicit mid-pilot)
- [ ] Poll `GET /health/pipeline` — must be **ok**. If **degraded**:
      check Redis ACI is `Running` (`az container show -g affectlearn-rg -n affectlearn-redis-aci`),
      then `az webapp restart -g affectlearn-rg -n affectlearn-api-2026`. (The worker now auto-recovers from transient Redis blips, but a dead Redis/ACI needs attention.)
- [ ] **Mid-pilot label-distribution check (the #1 pilot risk, PRD line 235):** export the `self_report` labels and inspect the class balance. If ≳80% are "engaged", intervene (re-brief participants, verify the widget) — do NOT wait until the end.
- [ ] Data quality: run `affectlearn-ml/training/behavioral/data_quality.py` on an interim export — flag degenerate (single-class) participants and sub-15-min sessions.
- [ ] Sequence-gap check per session (NFR23): `GET /api/v1/research/.../gaps` — large gaps hint at Redis drops.

## 5. Data targets
- [ ] ~10–15 participants × 60–90 min × 1–2 sessions ≈ **600–2,700 behavioral windows**.
- [ ] Split **by participant** (never by window) for train/val/test.
- [ ] Expect heavy class imbalance (engaged dominates) → class weighting is already on in training.

## 6. Post-pilot → train the behavioral model
- [ ] (Optional) set phase → phase_b for the adaptive arm, or conclude: `POST /api/v1/admin/study/phase`.
- [ ] **Export**: `GET /api/v1/research/phase-a-dataset` (admin) → JSON: behavioral feature windows (`payload.features`) + `self_report` labels.
- [ ] In `affectlearn-ml`: set `training/behavioral/config.yaml` → `data.use_synthetic: false`, `data.phase_a_export: <export.json>`; run `train_bilstm.py` in Colab (torch).
- [ ] Evaluate: per-class F1, **per-participant** accuracy, confusion matrix (literature range ~50–65%).
- [ ] Copy `behavioral_bilstm.onnx` + `behavioral_feature_stats.json` → `backend/models/`; redeploy.

---

### Quick reference
| Action | Command / URL |
|---|---|
| Pipeline health | `GET https://affectlearn-api-2026.azurewebsites.net/health/pipeline` |
| Assign group | `POST /api/v1/admin/study/groups` `{user_id, group}` |
| Lock groups (pilot begins) | `POST /api/v1/admin/study/groups/lock` |
| Get / set phase | `GET` / `POST /api/v1/admin/study/phase` |
| Export training set | `GET /api/v1/research/phase-a-dataset` |
| Reset-seed courses | `DATABASE_URL=<prod> python -m app.db.seed_courses --reset` |
| Restart backend | `az webapp restart -g affectlearn-rg -n affectlearn-api-2026` |
