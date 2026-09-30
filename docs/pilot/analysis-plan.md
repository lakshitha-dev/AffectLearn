# Analysis plan (pre-registration)

**Status:** DRAFT. Fix, date and send to the supervisor before the first participant. Anything
changed after the first participant is reported as a deviation.

Fixed on: `[DATE]` · Supervisor acknowledgement: `[DATE]`

## 0. Principles

- **This is a pilot.** Between arms at n = 30, only d ≥ 1.06 is detectable (n = 20: d ≥ 1.32).
  Results are reported as effect sizes with 95% confidence intervals, labelled as estimates.
  **No claim of effectiveness is made.**
- **The detectors' outputs are inferences, not ground truth.** Self-reports are a reference label
  and are themselves fallible. Agreement between the two is reported as agreement, never as
  "accuracy".
- **Satisfaction and UX scores describe experience.** They are not evidence that adaptation
  improves learning.
- **One principal comparison is declared (§3). Everything else is exploratory** and labelled so.
- **Every analysis is split by `config_version`** if more than one appears in the data.
- The data comes from `scripts/export_pilot.py` (see [data-dictionary.md](data-dictionary.md)).
  Analysis code lives in `affectlearn-ml/evaluation/pilot/`, using pandas, scipy and statsmodels.

## 1. Participant flow and exclusions

- Report enrolled, allocated, completed, withdrawn and technical failures per arm, from
  `participants.csv`.
- **Primary analysis set:** all participants with `end_reason = completed` and both knowledge
  tests.
- **Sensitivity analysis:** all allocated participants with any post-test.
- Sessions with a protocol deviation that affected the task are listed, and excluded in a second
  sensitivity analysis.

## 2. Feasibility (primary aims of the pilot)

Pre-set criteria. Each is reported as met or not met:

| Criterion | Target | Source |
|---|---|---|
| Behavioural windows received ÷ expected (task minutes × 2) | ≥ 90% | `detections.csv` |
| Facial cycles with a face present (among camera-on participants) | ≥ 70% | `detections.csv` (`face_ratio`, `empty_cycle`) |
| Sequence gaps in the research record | none unexplained | `/admin/research/events/gaps` |
| Delivered cards with a complete chain (detection → gate → strategy → delivery → rendered) | ≥ 95% | `decisions.csv` + `adaptations.csv` |
| LLM fallback rate (adaptive arm) | reported | `decisions.csv` (`fallback`) |
| Detection-to-render latency, median and 90th percentile | reported | `detections.csv` + `adaptations.csv` |
| Personal data in the export | none | manual check of every file |
| Withdrawals and distress incidents | reported | `participants.csv`, deviation log |

## 3. Principal comparison `[DECIDE with the supervisor]`

**Proposed:** learning gain between arms.

- **Outcome:** post-test score, adjusted for pre-test score. Also reported: normalised gain
  (post − pre) ÷ (max − pre).
- **Model:** ANCOVA, `post ~ pre + arm`. The arm effect is reported as Hedges' g, with a 95% CI
  from a 5,000-resample bootstrap.
- **Assumption checks:** residual normality and homogeneity of regression slopes. If violated,
  report a rank-based alternative (Quade) beside the ANCOVA.
- **Interpretation:** an effect-size estimate for planning a powered study, not a test of
  effectiveness.

## 4. System behaviour (exploratory)

1. **Facial channel.**
   - Per participant: the distribution of P(disengaged), how long states last, and transition
     rates.
   - Agreement with the nearest self-report within ±60 s (disengaged vs {bored, confused,
     frustrated}; engaged vs {engaged, neutral}): a confusion matrix, Cohen's κ, and AUC with a
     participant-clustered bootstrap CI.
2. **Behavioural channel.**
   - The distribution of P(confused), and the share of windows at or above the 0.70 floor
     (expected to be near 0).
   - Association with self-reported confusion.
   - For participants who opted into raw windows: exploratory re-derivation of features. No
     retraining claims are made from pilot data.
3. **Triggers.**
   - Offers per hour: delivered in the adaptive arm; `shadow_would_offer` in the control arm.
   - The distribution of gate reasons per arm.
   - The source of each offer: facial vs "I'm stuck" (`help_requested`). These are reported
     separately throughout.
4. **Responses to help** (adaptive arm).
   - Interaction outcome (accepted / dismissed / none) and probe answers (helped / did not help /
     unsure / dismissed / unanswered).
   - The next quiz attempt's correctness (`outcome_is_correct`).
   - Activity in the 120 s after `rendered_at` vs the 120 s before.
5. **Matched moments across arms.**
   - For every moment the gate would have offered help: a delivered offer in the adaptive arm, a
     `shadow_would_offer` moment in the control arm.
   - Compare the next self-report, the next quiz correctness and 120 s activity between arms.
   - Caveat, reported beside the result: the shadow assumes every passing moment would have been
     delivered, which slightly overstates the adaptive arm's opportunities.

## 5. Experience (exploratory)

- **SUS:** mean and 95% CI per arm, against the published benchmark of 68.
- **UEQ-S:** pragmatic and hedonic scale means per arm (−3..+3).
- **Satisfaction:** the four items, reported one by one.
- **Lesson feedback,** per arm, item by item:
  - "Noticed a change" rate. The control arm's rate is the baseline for reporting changes that
    did not happen.
  - Among those who noticed: helpfulness and distraction.
- **Debrief notes:** a brief thematic summary, with the number of participants per theme.

## 6. Missing data

- Report missingness per measure.
- No imputation for the principal comparison: complete cases, plus the §1 sensitivity analyses.
- Skipped self-reports and questionnaires are counted as skipped, not as missing at random.

## 7. What will not be claimed

- That adaptation improves learning, engagement or satisfaction.
- That the detectors are accurate on this platform (only agreement with self-report is reported).
- Anything about frustration: no detector for it exists on the platform.
