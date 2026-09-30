# Pilot protocol

Protocol version: **pilot-1.0**. Record it in each `pilot_sessions.protocol_version`. Consent text version: **2026-09-pilot-v1**.

## 1. Aims

1. **Feasibility.** Can the platform collect the following from real learners, in time order,
   without loss or privacy failure?
   - facial-geometry inferences;
   - behavioural interaction;
   - learning performance;
   - adaptation decisions;
   - self-reports and questionnaire answers.
2. **System behaviour.** How often do the detectors and the gate trigger help with real learners?
   What do learners do with the help? How do the detectors' outputs compare with learners' own
   self-reports?
3. **Effect-size estimation.** Estimate the difference between the adaptive and control arms in
   learning gain and user experience, with confidence intervals, to plan a properly powered study.
   The pilot is not designed or powered to establish effectiveness (see §9).

## 2. Design

**Two-arm, between-participants, single-blind randomised pilot.**

| | Control | Adaptive |
|---|---|---|
| Lessons, self-reports, questionnaires | Same | Same |
| Facial and behavioural sensing | Runs and is recorded | Runs and is recorded |
| Gate evaluation | Shadow only: recorded, never acted on | Live |
| Help cards (hint, breakdown, harder question, break, video…) | Never shown | Shown when the gate opens |
| "I'm stuck" button | Not shown (`[DECIDE]`, see §10) | Shown |
| Withholding within the arm | — | None (`ADAPT_WITHHOLD_RATE=0`) |

**Allocation.**
- Randomisation is seeded, in blocks of 4 (2 + 2).
- It is generated before enrolment by `scripts/create_pilot_participants.py --seed <SEED>`.
- Record the seed here: `[SEED]`.
- Participants are allocated in order of enrolment code (P001, P002, …).
- Group assignments are locked before the first participant.

**Blinding.**
- Participants are not told their arm.
- The facilitator knows it; this cannot be avoided. They therefore follow the script and do not
  intervene during the learning task.

**System configuration.**
- The deployed configuration is used (`docker-compose.pilot.yml`):
  - geometry facial model;
  - GBDT behavioural model;
  - performance channel (struggle heuristic) allowed to trigger help: a pilot-only setting,
    `[DECIDE]`, see §10;
  - floors: facial 0.70, behavioural 0.70, performance 0.45 (code default 0.60); global floor
    0.70;
  - persistence 2, cooldown 3, at most 6 offers per session;
  - actionable states: bored and confused;
  - gpt-4o via OpenAI.
- The configuration is locked before the first participant. Every event carries `config_version`.
- Any change mid-study is a protocol deviation and must be logged.

## 3. Participants

**Target:** `[DECIDE: n, 20–30]` adults. Participation is voluntary.

**Inclusion:**
- aged 18 or over;
- able to read English course material;
- has normal or corrected vision;
- is comfortable having the webcam on (the camera is optional, but those who decline are
  recorded as behaviour-only).

**Exclusion:**
- a current student whose grades the researcher or the supervisor can influence;
- anyone who has already taken the pilot course, or took part in a dry run.

**Recruitment:**
- the information sheet is sent at least 24 h before the session;
- there is no academic credit, penalty or grade effect;
- compensation: `[DECIDE]`.

## 4. Materials

- **Laptop and stack:** the researcher's laptop, running the local stack (see the checklist). The
  participant uses a Chrome **Guest** window at `http://localhost:3000`.
- **Course:**
  - a neutral warm-up section;
  - then the study course, in fixed order for everyone (`[COURSE]`, sections as seeded by
    `app.db.seed_courses`).
  - Some sections are written to feel slow, dense or confusing (`deploy/azure/AFFECT_SECTION_CODEBOOK.md`).
    The information sheet says so in general terms, and the debrief explains it.
- **Knowledge tests:** parallel pre- and post-test forms, seeded as the course's assessments. They
  must be checked for equal difficulty before the pilot (`[DECIDE]`).
- **Instruments:**
  - pre-study questionnaire (onboarding);
  - self-report bar every 2 sections (engaged, confused, bored, frustrated, neutral, or skip);
  - "Did that help?" probe, adaptive arm only, 30 s after a card;
  - lesson feedback after each lesson, both arms (`lesson_feedback` v1.0);
  - 4-item satisfaction survey;
  - SUS;
  - UEQ-S.

## 5. Procedure (about 70 minutes)

| # | Step | Min | Record |
|---|---|---|---|
| 0 | Set-up before arrival (checklist §B) | 10 | Readiness check passed |
| 1 | Welcome, scripted briefing | 5 | — |
| 2 | Paper consent form (the only place the name appears). The participant code is written on the linking sheet. | 5 | Linking sheet |
| 3 | The facilitator starts the sitting: `POST /api/v1/admin/pilot/sessions` | 1 | `pilot_sessions` row |
| 4 | Sign in with the prepared account. The facilitator types the credentials. | 1 | — |
| 5 | In-app consent, including the optional raw-record scope. Then the webcam choice and calibration. | 3 | `users.consent_*`, `webcam_enabled` |
| 6 | Pre-study questionnaire and knowledge pre-test | 8 | `questionnaire_responses`, assessment attempt |
| 7 | Warm-up section (baseline) | 3 | — |
| 8 | Main task: the study course in fixed order, time-boxed to `[35–40]` min. The facilitator sits out of view and silent. **No think-aloud**: talking moves `mouth_open`, which is a model feature. | 35–40 | All channels |
| 9 | Knowledge post-test | 5 | Assessment attempt |
| 10 | Satisfaction, then SUS, then UEQ-S (same order for everyone) | 7 | `survey_responses`, `instrument_responses` |
| 11 | Debrief and a short semi-structured interview (notes only, no recording) | 5–10 | Facilitator notes |
| 12 | End the sitting (`completed`, `withdrawn`, `technical`) with any deviation notes. Log out and close the Guest window. Check the camera light is off. | 2 | `pilot_sessions.end_reason` |

**Debrief content:**
- the study's purpose and the two arms;
- that some material was written to feel slow or confusing;
- that the camera and behaviour readings are a computer's guesses;
- the withdrawal deadline `[DECIDE]` and how to withdraw.

## 6. Stopping and adverse events

**Stopping:**
- A participant may stop at any time without giving a reason:
  - by saying so;
  - with "Stop taking part" on the profile page (all capture stops within about 10 s);
  - or by switching the camera off.
- If the participant asks, erase their data with `POST /api/v1/admin/users/{id}/withdraw`.
  Otherwise keep what was collected, as they choose.
- End the sitting as `withdrawn`.

**Distress** (for example, frustration with the content):
- stop the session;
- debrief;
- record the incident in `deviation_notes`;
- inform the supervisor.

**Technical failure:**
- end the sitting as `technical`, with a note;
- do not re-run the same participant on the same course;
- analysis follows §8 of the analysis plan.

## 7. Dry runs

Before enrolment, run 2–3 dry runs with volunteers who are not participants:
- use the readiness account or extra demo-flagged accounts;
- they are excluded from the data;
- they check timing, wording and the full export.

## 8. Data

See [data-management-plan.md](data-management-plan.md). No video or images are stored.

## 9. Power and interpretation

**Detectable effects.** Between arms, at α = .05 and power .80:
- n = 30 detects only d ≥ 1.06;
- n = 20 detects only d ≥ 1.32 (thesis Table 3.4).

**How results are reported:**
- as effect sizes with 95% confidence intervals;
- labelled as pilot estimates;
- positive satisfaction or UX scores are not evidence that adaptation improves learning.

## 10. Open decisions (`[DECIDE]`)

1. Formal ethics committee review before enrolment. The proposal promised NSBM committee
   approval; `PHASE_A_RUN_CHECKLIST.md` treats it as the hard gate.
2. The primary outcome (see the analysis plan).
3. Treatment definition: should control also get "I'm stuck"? The alternatives:
   - keep it adaptive-only: the treatment is detector-triggered help plus on-demand help;
   - give both arms on-demand help: this isolates the detector-triggered part, but needs a code
     change to show the button to control and route it to the same agents.
4. Retention periods, withdrawal deadline, target n, compensation.
5. The performance channel as a trigger. The pilot configuration lets it trigger help, because
   the behavioural model never reaches its floor on this platform. Without it, automatic
   confusion help would not exist. To confirm:
   - promoting an unfitted heuristic before any pilot data. The alternative is to keep it
     advisory, so that the gate only records `channel_advisory` when it would have helped;
   - the 0.45 floor, which is the channel's own reporting score (the code default is 0.60). Each
     quiz takes one answer and most sections have at most one quiz, so a wrong answer adds 0.12.
     At 0.60 the channel could fire on only 14 of the 56 sections, and only with three re-reads
     and very slow reading. At 0.45 it needs at least two indicators together, for example a
     revealed answer plus 3 re-reads, or 1 wrong answer plus 2 re-reads plus slow reading. It is
     reachable on 38 of the 56 sections;
   - the counters are cumulative for a section. Once a section crosses the floor it stays over
     it, and only the help ladder, "Got it" (resolved) and the card holds limit repeat offers
     there.
