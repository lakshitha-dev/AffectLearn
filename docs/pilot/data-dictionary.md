# Data dictionary — pilot export

`scripts/export_pilot.py --out <dir>` writes the files below. The export is pseudonymised:
- learner UUIDs are replaced by participant codes (`code`);
- no e-mail, name or password appears;
- demo accounts, and learners without a pilot sitting, are excluded.

Times are Unix milliseconds on the server clock, unless marked `_at` (ISO 8601, UTC) or
`client_*` (the browser clock). The browser and server run on the same laptop in the pilot, so the
two clocks agree.

## Join keys

| Key | Links |
|---|---|
| `code` | everything belonging to one participant |
| `decision_id` | one graph run: a detection → its gate verdict → strategy → content → delivery, and the ledger row and raw window of that run |
| `adaptation_id` | one delivered card → its lifecycle events, interaction, probe answer and the quiz attempt answered while it was on screen (`assistance_id`) |
| `event_id` | one research event (unique; used for de-duplication) |
| `page_instance_id` | one lesson-page mount (raw windows), since cycle numbers restart per page |
| `config_version` | the configuration in force; split analyses by it |

## Files

**`participants.csv`**: one row per sitting.
- `arm`, `phase`, `protocol_version`, `consent_version`;
- `consent_scopes` (JSON: `behavioural`, `raw_interaction`), `webcam_enabled`,
  `consent_withdrawn_at`;
- `config_version_at_start`, `started_at`, `ended_at`;
- `end_reason` (`completed` | `withdrawn` | `technical` | `other`);
- `device` (JSON), `deviation_notes`.

**`timeline.csv`**: every research event, ordered by `timestamp`.
- `event_id`, `decision_id`, `code`, `event_type`, `timestamp`, `session_id`, `sequence_number`,
  `cycle_number`;
- `course_id`, `section_id`, `block_id`, `phase`, `group`, `config_version`;
- `payload` (JSON; the fields depend on `event_type`, listed below).

**`detections.csv`**: model inferences, one row per reading.
- `event_type` (`facial_affect_detected` | `behavioral_affect_detected` |
  `performance_signal_detected`);
- timing: `timestamp` (emit), `received_at_ms` (window reached the server),
  `client_window_start` / `client_window_end` (capture interval), `graph_ms`;
- the reading: `model_kind`, `affect_source`, `affect_state`, `affect_confidence`, `p_disengaged`
  (facial), `p_confused` (behavioural), `probs`;
- facial context: `face_ratio`, `frames_with_face`, `empty_cycle` (no face all cycle);
- behavioural context: `idle` (no activity);
- `error`;
- `geometry_features` (JSON, the 20 values the facial model scored).

**`decisions.csv`**: one row per gate verdict (`learner_profile_updated`).
- `affect_source`, `affect_state`, `affect_confidence`, `min_confidence_applied`,
  `decisive_channel`;
- `gate`: the reason code, e.g. `ok`, `not_sustained`, `cooldown`, `low_confidence`,
  `channel_advisory`, `card_open`, `session_cap`, `not_eligible`;
- `arm` (`delivered` | `withheld` | empty);
- `shadow_gate` / `shadow_would_offer`: **control arm only**, the adaptive arm's verdict for the
  same moment;
- joined from the same run: `action`, `llm_model`, `llm_ms`, `fallback`, `adaptation_id`,
  `delivered_at_ms`.

**`adaptations.csv`**: one row per card in the ledger.
- `adaptation_id`, `decision_id`, `section_id`, `group`;
- what triggered it: `affect_state`, `affect_source`, `affect_confidence`, `gate_reason`;
- what it was: `action_type`, `generated`, `fallback`;
- delivery: `delivered_at`, `delivery_failed`, `rendered_at_ms` (first visible on screen);
- response: `interaction` (`accepted` | `dismissed` | `applied`), `interacted_at`;
- probe: `probe_response` (`helped` | `did_not_help` | `unsure`), `probe_dismissed`;
- outcome: `outcome_is_correct` (the next answer while it was shown).

**`self_reports.csv`**: `timestamp`, `section_id`, `cycle_number`, `group`, `affect` (engaged |
confused | bored | frustrated | neutral), `skipped`, `prompt_index`.

**`learning.csv`**: attempts, identified by `kind`.
- `block_attempt`: quiz and exercise answers, graded on the server. Fields: `block_id`,
  `section_id`, `attempt_number`, `is_correct`, `response_time_ms`, `assistance_id`,
  `submitted_at`.
- `assessment`: pre and post tests. Fields: `assessment_id`, `attempt_number`, `score`,
  `max_score`, `started_at`, `submitted_at`.

**`instruments.csv`**: one row per questionnaire administration.
- `instrument` (`lesson_feedback` | `sus` | `ueq_s`), `instrument_version`, `context` (JSON, e.g.
  `lessonId`), `skipped`, `shown_at`, `submitted_at`, `responses` (JSON);
- scores: `sus_score` (0–100), `ueq_pragmatic` / `ueq_hedonic` / `ueq_overall` (−3..+3).

**`raw_windows.jsonl`**: opt-in participants only. One JSON object per 30 s window.
- `events`: the model's input stream (`mouse_sample`, `mouse_click` with `target`, `key` with
  `category`, `scroll`, `visibility`);
- `ui_events`: `hover` {`target`, `enter_t_wall`, `dwell_ms`} and `clipboard` {`action`,
  `target`};
- `viewport` {`w`, `h`, `doc_h`, `dpr`};
- `page_instance_id`, `decision_id`, capture times.

## Research event types (in `timeline.csv`)

| `event_type` | When | Key payload fields |
|---|---|---|
| `ws_connected` / `ws_reconnected` / `ws_session_restored` | socket opened | |
| `session_provenance` | socket opened | `models` (paths and SHA-256), `gate` (effective config), `llm`, `app_commit`, `user_agent` |
| `facial_affect_detected` | each facial window | see `detections.csv` |
| `behavioral_affect_detected` | each behavioural window | `features` (30×16), `event_counts`, `idle` |
| `performance_signal_detected` | struggle counters above threshold | `breakdown`, `counts` |
| `multimodal_affect_detected` | a facial and a behavioural reading paired | fused probabilities (advisory only) |
| `learner_profile_updated` | each gate verdict | see `decisions.csv` |
| `strategy_decided` | adaptive arm, gate passed | `action_type`, `urgency`, `reason`, `llm_model`, `llm_ms`, `fallback` |
| `adaptation_triggered` | content produced | `text`, `generated`, `fallback`, `llm_model`, `llm_ms` |
| `adaptation_delivered` / `adaptation_delivery_failed` / `adaptation_dropped` | card sent / failed / stale | `adaptation_id`, `action` |
| `adaptation_lifecycle` | card first rendered, re-opened, expanded or collapsed; probe shown or unanswered; break taken, declined, returned early or completed | `adaptation_id`, `event`, `since_received_ms`, `seconds_away` |
| `adaptation_interaction` | "Got it", dismiss, accept | `adaptation_id`, `interaction` |
| `adaptation_probe` | "Did that help?" answered or dismissed | `response`, `dismissed`, `shown_after_ms` |
| `help_requested` | "I'm stuck" / "Still stuck" / "move on" | `request`, `from_adaptation_id` |
| `self_report` | feeling check-in | `affect`, `skipped` |
| `quiz_submitted` | quiz or exercise answer | `is_correct`, `graded_by`, `client_is_correct`, `block_type`, `attempt_number` |
| `instrument_submitted` | questionnaire | `instrument`, `responses`, `sus_score` / `ueq_s` |
| `pilot_session_started` / `pilot_session_ended` | facilitator | `participant_code`, `end_reason` |
| `section_started` / `section_completed` / `section_features` | section progress | completion and the per-section interaction counters |
| `exercise_attempted` | exercise activity (e.g. "Show answer") | `block_id` |
| `video_resource_selected` | the Video sub-agent picked a video | `video_id`, `reason` |
| `questionnaire_submitted` / `survey_completed` | pre-study questionnaire / satisfaction survey | responses (mean score for the survey) |
| `ws_disconnected` | socket closed | `reason`, `duration_ms` |
| `phase_transition`, configuration changes | admin changes | audit |

## Known limitations of the record

- The last partial behavioural and facial window of each lesson page (up to 30 s) is not sent.
  Sending it would give the model a sub-30 s window, and the socket is already closing when the
  page unmounts.
- The control arm's `shadow_would_offer` assumes every passing moment would have been delivered.
- The behavioural model's mouse normalisation assumes a 1920×1080 viewport, as it was trained. The
  real viewport is recorded in raw windows for analysis only.
