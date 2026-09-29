# Data management plan — pilot

## What is collected, and what is not

| Data | Where it is stored | Personal? | Notes |
|---|---|---|---|
| Name, signature | Paper consent form, paper linking sheet | Yes | Never entered on the laptop. |
| Study account | `users`: code-derived e-mail `p007@pilot.affectlearn.io`, first name "P007", consent version and scopes, webcam choice | Pseudonymous | No real e-mail or name. |
| Facial geometry inferences | `research_events` (`facial_affect_detected`): label, probabilities, 20 aggregate geometry features, face presence | Pseudonymous | **No images, video or per-frame geometry are stored.** Frames exist only in browser memory. |
| Behavioural features | `research_events` (`behavioral_affect_detected`): 30×16 feature window | Pseudonymous | |
| Raw interaction windows | `raw_interaction_windows`: pointer positions, clicks with element ids, scrolls, key **categories** with timing, hover dwell, clipboard actions (no content) | Pseudonymous | **Opt-in only** (`raw_interaction` consent scope). Never key values, typed text, clipboard content or password fields. |
| Learning | `quiz_attempts` (server-graded; includes typed exercise answers), `assessment_attempts`, `section_visits`, `section_progress` | Pseudonymous | Exercise answers are the participant's own words, so treat them as potentially identifying. |
| Adaptation | `research_events` (gate, strategy, content, delivery, lifecycle), `assistance_events` | Pseudonymous | Includes the help text shown. |
| Self-report and questionnaires | `research_events` (`self_report`, `adaptation_probe`), `questionnaire_responses`, `survey_responses`, `instrument_responses` | Pseudonymous | The pre-questionnaire asks for age range and gender (with "Prefer not to say"). |
| Sitting records | `pilot_sessions` | Pseudonymous | Deviation notes must not contain names. |
| Interview notes | Paper, against the code | Pseudonymous | Not typed onto the laptop unless needed; if typed, stored with the export. |

## Third parties

- **OpenAI (gpt-4o):** receives the section text, the estimated state and recent section activity,
  for the adaptive arm only. No name, e-mail or account id is sent (pinned by
  `tests/agents/test_prompt_privacy.py`). `[CHECK]` OpenAI's current API data-retention terms, and
  whether sending this data counts as a cross-border transfer requiring disclosure under Sri Lanka's
  PDPA (No. 9 of 2022).
- **YouTube:** a topic search and, if a video is opened, the embedded player (youtube-nocookie).
- **Google / jsDelivr:** serve the MediaPipe code and model files. No camera data is sent to them.
- **Google Analytics:** not enabled in the pilot build.

## Where the data lives, and who can access it

- **Postgres** runs in a Docker volume on the encrypted pilot laptop. Postgres and Redis are not
  published on the network; the app ports bind to `127.0.0.1` only.
- **Access:**
  - the researcher, through the admin account (strong password in `.env.pilot`);
  - the supervisor, on request.
  - No designer accounts are used.
- **Exports and backups:** encrypted archives, stored off the laptop in `[LOCATION]`.
- **Container logs** carry event envelopes but not payloads (`RESEARCH_LOG_PAYLOADS=0`). They are
  cleared after each session day.

## Retention and deletion `[DECIDE]`

| Data | Kept until | Then |
|---|---|---|
| Paper linking sheet | The withdrawal deadline, `[DATE]` | Shredded; the data becomes non-linkable |
| `pilot_accounts.csv` (passwords) | End of data collection | Deleted |
| Raw interaction windows | `[e.g. after assessment of the project]` | `DELETE FROM raw_interaction_windows` |
| Other pseudonymised research data | `[per NSBM research data policy]` | Database volume and backups destroyed |

**Withdrawal before the deadline** uses `POST /api/v1/admin/users/{id}/withdraw` (or the
participant's own "Delete account"). It removes:
- the account and every table keyed to it, including the raw windows;
- the learner's research events;
- the learner's cached Redis state.

Stream entries still queued are dropped by the worker. Backups taken before the withdrawal must be
handled too: either restore-and-erase, or record the withdrawal so the data is excluded at analysis.

The automatic research-event purge (`RESEARCH_RETENTION_DAYS`) is **off** in the pilot. It would
also delete the phase and configuration audit events, so deletion follows the schedule above
instead.

## Reporting

- Results are reported only in aggregate or by participant code.
- Facial and behavioural outputs are described as model inferences; self-reports are described as
  reference labels. Neither is ground truth.
