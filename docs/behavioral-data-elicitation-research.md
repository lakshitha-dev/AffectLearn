# Ethically Eliciting Boredom, Confusion, Engagement & Frustration for Behavioral-Data Collection
### A research-backed design analysis for AffectLearn

*Compiled 2026-07-04. Evidence-based claims are cited; ideas that are original proposals are flagged **[NOVEL]**. Recommendations map to AffectLearn's existing design (47 affect-tagged sections, ~30 s behavioral window, gated quizzes, self-report bar every 2 sections).*

---

## Part 1 — The theory: what triggers each state

These four states are **not independent** — they form a dynamic system. D'Mello & Graesser describe **two cycles**: a *virtuous* one, **engaged ⇄ confused** (impasse, then resolved back to flow), and a *vicious* one, **engaged → confused → frustrated → bored** when confusion is not resolved. ([D'Mello & Graesser, *Dynamics of affective states during complex learning*](https://eric.ed.gov/?id=EJ950444); [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0959475211000806))

Appraisal levers per state:

| State | Root cause (appraisal) | Design lever |
|---|---|---|
| **Engaged / flow** | control high, value high | clear goal, achievable challenge, relevance, feedback |
| **Confused** | cognitive disequilibrium — contradiction/anomaly/impasse ([D'Mello & Graesser, *Confusion*](https://home.cs.colorado.edu/~mozer/Teaching/syllabi/TopicsInCognitiveScienceSpring2016/DMelloConfusion-Reprint.pdf)) | introduce a genuine, resolvable gap |
| **Frustrated** | control drops — persistent unresolved impasse | hard task, blocked progress |
| **Bored** | value low — monotony, under/over-challenge ([Pekrun, CVT](https://link.springer.com/article/10.1007/s10648-006-9029-9)) | low-stimulation, repetitive, no payoff |

Two design-shaping findings:
1. **Boredom is the dangerous state, not frustration.** Boredom is highly *persistent* and linked to poorer learning + *gaming the system*; frustration is *less persistent* and NOT an antecedent to gaming; confusion and engaged concentration are the most common states. ([*Better to be frustrated than bored*, IJHCS 2010](https://www.sciencedirect.com/science/article/abs/pii/S1071581909001797))
2. **Confusion is only useful if resolvable.** Productive confusion must be task-relevant, scaffolded, and eventually resolved; persistent/hopeless confusion decays into frustration→boredom. ([*Confusion can be beneficial for learning*](https://www.sciencedirect.com/science/article/abs/pii/S0959475212000357); [*Not all confusion is productive*](https://www.researchgate.net/publication/340557060)) → `confused` sections MUST have a resolution path.

---

## Part 2a — Per-state elicitation catalog (ranked by evidence) → mapped to AffectLearn

**CONFUSED (strongest experimental base):**
- ★★★ Contradictions / conflicting information ([*Inducing & Tracking Confusion with Contradictions*](https://files.eric.ed.gov/fulltext/EJ1190004.pdf)) → add a callout that appears to contradict the prior paragraph, resolve a section later.
- ★★★ Impasse / breakdown scenarios (a worked example that "breaks") → in *Design and Trace the Agent*, show a trace that fails and ask why.
- ★★☆ Dense notation too fast (already used: MDP/POMDP, BFT n≥3f+1) — keep resolvable.
- ⚠️ False feedback: validated but higher ethical cost — **avoid**.

**BORED (well-grounded, lowest ethical risk):**
- ★★★ Monotony + low value: long uniform low-challenge text, no interaction, no payoff ([Pekrun CVT](https://link.springer.com/article/10.1007/s10648-006-9029-9)) → your taxonomies (*Catalogue of Memory Types*, *Message Envelope Field Reference*, *Glossary of Evaluation Metrics*) are textbook; strengthen by stripping all diagrams/interaction.
- ★★☆ Under-challenge / repetition of known content.

**FRUSTRATED (effective; keep mild + recoverable):**
- ★★★ Solvable-but-hard task with blocked progress → gated quizzes with tricky distractors; gating itself amplifies frustration — use deliberately, bound it.
- ★★☆ Effort–reward mismatch (slow-moving progress bar). **[NOVEL/speculative]**

**ENGAGED (control/baseline):**
- ★★★ Optimal challenge + clarity + relevance + feedback (flow) → diagram + analogy + fair quiz with immediate positive feedback.

---

## Part 2b — Behavior ↔ state evidence table (signals AffectLearn captures)

*Honesty caveat: keystroke/mouse affect detection typically reports ~70%+ accuracy but is often NOT replicated across contexts and is person-dependent — treat as priors to validate against your own self-reports.* ([review](https://www.researchgate.net/publication/261480224); [engagement mining](https://link.springer.com/chapter/10.1007/978-3-030-16469-0_3); [Frustrometer](https://arxiv.org/pdf/2606.13687))

| Signal | Boredom | Confusion | Frustration | Engagement |
|---|---|---|---|---|
| Idle / long mouse-idle | ↑↑ | ↑ | — | ↓ |
| Time-on-section vs baseline | ↑ (disengaged) | ↑ (re-read) | ↑ | baseline |
| Scroll pattern | skim / none | back-scroll | erratic | steady |
| Mouse speed & precision | slow/idle | — | ↑speed ↓precision | smooth |
| Click rate / off-target | low | ↑ | ↑↑ | moderate |
| Backspace rate | low | ↑ | ↑↑ | low |
| Typing speed | ↓ | ↓ | variable | steady |
| Quiz attempts / retries | rapid guessing | multiple tries | retries + long pause | first-try correct |
| Rapid wrong answers (gaming) | ↑↑ **boredom marker** | — | — | — |
| Tab-visibility (leaving tab) | ↑↑ | — | ↑ | ↓ |

Best fingerprints: **boredom** = gaming + long idle + tab-away; **frustration** = ↑backspace + ↑click-rate + fast/imprecise mouse + quiz retries; **confusion** = back-scroll + longer dwell + exploring clicks; **engagement** = steady at personal baseline.

---

## Part 2c — Ethics guardrail checklist (grounded in published practice)

Inducing mild negative affect for learning research is standard and IRB-approvable (the confusion-induction studies all did it). Guardrails:
- ☑ Consent says material "may at times feel difficult, tedious, or confusing" (honest, without revealing the specific manipulation → avoids demand characteristics).
- ☑ Keep mild + recoverable; every confused/frustrated section has a resolution (next section clarifies; quiz shows answer + explanation).
- ☑ No harmful deception / no person-directed false feedback (content contradictions are ethically lighter).
- ☑ Right to withdraw + skip (self-report Skip; can leave anytime).
- ☑ Debrief on completion (sections varied difficulty/interest; goal was studying emotion, not testing them).
- ☑ Cap consecutive negative-affect sections; interleave engaged sections.
- ☑ Data minimization (already: keystroke category only, no video stored, consent-gated).

---

## Part 2d — Bias-minimization protocol

Threats: Hawthorne/demand characteristics + self-report reactivity. ([reactivity](https://pmc.ncbi.nlm.nih.gov/articles/PMC5241226/); [Hawthorne](https://www.scribbr.com/research-bias/hawthorne-effect/); [demand characteristics](https://www.simplypsychology.org/demand-characteristics.html))
1. **Counterbalance affect-section order per participant** (fixed order confounds fatigue with affect) — strongest single fix.
2. **Per-participant baseline**: ~2–3 min neutral reading first; normalize all signals per person (individual differences dominate).
3. **Neutral framing** ("a course we're studying", not "we'll bore you").
4. **Watch self-report reactivity**: keep prompt one-click; treat as subset ground-truth; randomly omit ~20% of prompts to estimate the prompt's own effect.
5. **Within-subject design** (each learner hits all 4 states → own control). A/B split stays orthogonal.
6. **Discard the first section** (novelty artifact).

---

## Part 2e — NOVEL proposals **[flagged: evidence-adjacent vs speculative]**

- **[evidence-adjacent] Reading-speed-normalized dwell probe** — `time_on_section / expected_reading_time` per person; >2× + back-scroll → confusion; >2× + idle/tab-away → boredom; <0.3× + wrong quiz → gaming/boredom.
- **[evidence-adjacent] Quiz-retry latency probe** — time-to-first-answer + retry count + inter-retry pause; long pause + retries + rising clicks = frustration.
- **[speculative] Micro-friction moment** — one fiddly-but-fair interaction in frustrated sections (motor behavior under mild friction is rich signal; must stay solvable).
- **[speculative] Boredom escape-hatch telemetry** — optional "skip to summary" link in bored sections; whether/when reached-for is itself a boredom label (and ethical).
- **[speculative] Scroll-velocity entropy** — variability of scroll speed; smooth=engaged, jittery=confusion, flat=boredom. New Bi-LSTM feature.
- **[evidence-adjacent] Confusion resolution capture** — after each confused section, log first-try correctness of the clarifying quiz → distinguishes productive vs hopeless confusion (a two-class label; likely improves model quality).

---

## Part 2f — Prioritized implementation action list

1. Counterbalance affect-section order per participant (biggest validity win).
2. Add a 2–3 min neutral calibration/baseline task; normalize signals per person.
3. Instrument quiz-retry latency + count + inter-retry pause (frustration probe — quizzes already gated).
4. Guarantee a resolution path after every `confused` section + capture follow-up quiz first-try correctness.
5. Add reading-speed-normalized dwell + scroll-velocity-entropy features.
6. Update consent + debrief copy per the checklist.
7. Randomly omit ~20% of self-report prompts to estimate prompt reactivity.
8. Cap consecutive negative-affect sections; interleave engaged.

---

## Sources
- D'Mello & Graesser, *Dynamics of affective states during complex learning* — [ERIC](https://eric.ed.gov/?id=EJ950444), [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0959475211000806)
- D'Mello & Graesser, *Confusion* (chapter) — [PDF](https://home.cs.colorado.edu/~mozer/Teaching/syllabi/TopicsInCognitiveScienceSpring2016/DMelloConfusion-Reprint.pdf)
- Baker, D'Mello, Rodrigo & Graesser, *Better to be frustrated than bored* (IJHCS 2010) — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1071581909001797)
- *Inducing and Tracking Confusion with Contradictions during Complex Learning* — [PDF](https://files.eric.ed.gov/fulltext/EJ1190004.pdf)
- D'Mello, Lehman, Pekrun & Graesser, *Confusion can be beneficial for learning* (L&I 2014) — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0959475212000357)
- *Not all confusion is productive* — [ResearchGate](https://www.researchgate.net/publication/340557060)
- Pekrun, *The Control-Value Theory of Achievement Emotions* (Educ Psych Rev 2006) — [Springer](https://link.springer.com/article/10.1007/s10648-006-9029-9)
- *A review of emotion recognition methods based on keystroke dynamics and mouse movements* — [ResearchGate](https://www.researchgate.net/publication/261480224)
- *Mining Keystroke & Mouse Dynamics to Increase Engagement* — [Springer](https://link.springer.com/chapter/10.1007/978-3-030-16469-0_3)
- *The Frustrometer: Detecting User Frustration…* — [arXiv](https://arxiv.org/pdf/2606.13687)
- Affective sequences within Reasoning Mind — [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC7334159/)
- Measurement reactivity in RCTs — [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC5241226/)
- Hawthorne effect — [Scribbr](https://www.scribbr.com/research-bias/hawthorne-effect/); Demand characteristics — [SimplyPsychology](https://www.simplypsychology.org/demand-characteristics.html)
