"""Runtime-editable system configuration, as a singleton (admin settings page).

WHY THIS TABLE EXISTS

Every knob governing the study — the trial withhold rate, the per-channel confidence floors, which
channels may act — was an environment variable set in Azure. Changing one meant editing app
settings and restarting the process: slow, invisible to the research record, and impossible to do
safely once collection has begun.

A dedicated SINGLETON table rather than a generic key/value store, following `StudyPhase`, which
made the same choice for the same stated reason: auditability. One row with named columns can be
read, migrated and reasoned about; a bag of strings cannot.

TWO GUARDS, BECAUSE EDITABLE THRESHOLDS ARE A RESEARCH HAZARD

If a confidence floor or the withhold rate changes halfway through data collection, the cycles
before and after are no longer comparable — and nothing in the dataset would show that it had
happened. An analysis would silently pool incomparable observations and report a result.

  * `version` increments on EVERY change and is stamped onto every research event, so a mid-study
    change becomes visible in the data and the analysis can be split on it.
  * `locked_at` makes changes refuse outright once collection starts. Unlocking is deliberate and
    recorded, exactly as `StudyGroup.locked_at` works for cohort assignment.

`values` HOLDS ONLY OVERRIDES

Not a full snapshot of the configuration. A key absent from `values` keeps whatever the environment
or the code default supplies, which means a fresh deploy against an empty row behaves exactly as
the deployment did before this table existed. It also lets the settings page distinguish "0.70,
the default" from "0.70, explicitly chosen" — a distinction that matters when reporting the study's
configuration in a thesis.

THE API KEY IS WRITE-ONLY

`llm_api_key_encrypted` is Fernet ciphertext and is never returned by any endpoint. `llm_api_key_hint`
holds the last four characters so an admin can confirm WHICH key is installed without the system
being able to disclose it. There is no code path that decrypts it for display.
"""

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text

from app.models.base import BaseModel


class SystemConfig(BaseModel):
    __tablename__ = "system_config"

    #: Bumped on every mutation, including a lock or a key rotation. Stamped onto every research
    #: event, so "which configuration produced this row" is answerable from the dataset alone.
    version = Column(Integer, nullable=False, default=1, server_default="1")

    #: ONLY the keys an admin has explicitly overridden. Absent key -> env/code default.
    #: Plain JSON rather than JSONB, matching `research_event.payload`: the test suite builds
    #: tables on SQLite via `create_all`, where JSONB does not exist. This row is always read
    #: whole, so there is nothing to gain from indexing inside it.
    values = Column(JSON, nullable=False, default=dict, server_default="{}")

    #: Non-null once collection has begun; blocks mutation until an explicit unlock.
    locked_at = Column(DateTime(timezone=True), nullable=True)

    #: Fernet ciphertext. Never returned by any endpoint, never logged.
    llm_api_key_encrypted = Column(Text, nullable=True)
    #: Last four characters only, so an admin can identify the installed key without disclosure.
    llm_api_key_hint = Column(String(8), nullable=True)
    llm_api_key_updated_at = Column(DateTime(timezone=True), nullable=True)
