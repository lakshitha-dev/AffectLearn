# AffectLearn pilot study — documents

The first study of AffectLearn with real participants. It runs in person, on the researcher's laptop,
and compares two arms: **control** (no adaptation) and **adaptive**. Each participant uses their
own real webcam, mouse and keyboard in a normal Chrome window.

| Document | For | What it is |
|---|---|---|
| [protocol.md](protocol.md) | researcher, supervisor, ethics review | Design, arms, procedure, timing, stopping rules |
| [information-sheet.md](information-sheet.md) | participants (given ≥ 24 h ahead) | Plain-language description of the study and the data |
| [consent-form.md](consent-form.md) | participants (signed on paper) | The consent statements, one per scope |
| [facilitator-script.md](facilitator-script.md) | facilitator | The words said in every session, in order |
| [PILOT_RUN_CHECKLIST.md](PILOT_RUN_CHECKLIST.md) | facilitator | Stack setup, pre-session checks, per-participant steps, after-session steps. Each step is also a one-line `..\..\pilot.ps1` command. |
| [data-management-plan.md](data-management-plan.md) | researcher, supervisor, ethics review | What data is held, where, who can see it, retention and deletion |
| [analysis-plan.md](analysis-plan.md) | researcher, supervisor | The pre-registered analysis: fix it before the first participant |
| [data-dictionary.md](data-dictionary.md) | analyst | Every exported file and field, and the research event types |

**Before any participant is enrolled, the items marked `[DECIDE]` must be resolved.** They are
decisions for the researcher, the supervisor or the ethics process, not for the code:

- whether the study needs formal ethics review;
- the primary outcome;
- whether the control arm also gets the "I'm stuck" button;
- whether the performance channel may trigger help, and at what floor (see below);
- the retention periods and the withdrawal deadline;
- the target number of participants;
- compensation.

**Two things the pilot cannot show, stated up front:**

- **Automatic confusion help comes from a heuristic, not a model.** The facial channel detects
  only engaged vs disengaged. The behavioural confusion model almost never reaches its 0.70 floor
  on this platform (live maximum 0.63 over 30 days). The pilot configuration therefore lets the
  performance channel trigger help. This channel is a hand-weighted count of wrong answers, a
  revealed answer, going back to re-read and slow reading, with a floor of 0.60. Its weights were
  chosen for face validity and have not been fitted. The adaptive arm's help will come from three
  sources: facial disengagement, the performance channel, and the learner pressing "I'm stuck".
  This is a pilot-only setting; everywhere else the performance channel stays advisory.
- **The sample is too small to test effectiveness.** With 20–30 participants split between two
  arms, only very large effects are detectable (d ≥ 1.06 at n = 30). The pilot estimates effect
  sizes and tests feasibility. It is not an effectiveness trial.
