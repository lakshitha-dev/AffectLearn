"""Durable research event store (Story 4.7; phase/group added in Story 6.5).

Every affect classification, agent decision, and interaction is persisted here for thesis
analysis. `sequence_number` is monotonic per `session_id` so dropped events are detectable
(NFR23). Populated by the background worker draining the Redis Stream.

Story 6.5 adds nullable, indexed `phase` and `group` columns so the dataset is filterable by
study phase (Phase A / Phase B) and A/B cohort. The 4.7 envelope (event_type, learner_id,
session_id, cycle_number, timestamp, sequence_number, payload) is unchanged.

Migration 021 adds the CONTENT COORDINATES -- `course_id`, `section_id`, `block_id` -- for the
same reason phase/group were promoted out of the payload: they are join keys, not attributes.
Until this, affect and adaptation rows were keyed by `session_id` + `cycle_number` only, so
nothing could say WHERE IN THE COURSE a cycle happened. `analytics_service` documents the
consequence in its own header: it falls back to `section_progress.affect_states`, a
client-supplied list posted on completion, because the model's own output could not be keyed
to a section. All three are nullable -- connection-level events (`ws_connected`) and
account-level ones (`questionnaire_submitted`) have no content coordinate, and historical rows
predate the column -- and indexed, because every per-section aggregate filters on them.

They are strings rather than UUID foreign keys deliberately: `research_events` is an append-only
research record whose rows must survive the deletion of the content they refer to (a designer
removing a section must not cascade away the evidence of what learners did in it).

NOTE: through Story 6.4 no alembic migration created this table (it was a deploy forward-item;
tests build it via `Base.metadata.create_all`). Migration `016` (Story 6.5) is the first to
`create_table` for `research_events`, then add the `phase`/`group` columns + indexes.
"""

from sqlalchemy import JSON, BigInteger, Column, Integer, String

from app.models.base import BaseModel


class ResearchEvent(BaseModel):
    __tablename__ = "research_events"

    event_type = Column(String(64), nullable=False, index=True)
    learner_id = Column(String(64), nullable=True, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    cycle_number = Column(Integer, nullable=False, default=0)
    timestamp = Column(BigInteger, nullable=False)        # unix ms
    sequence_number = Column(Integer, nullable=True)      # monotonic per session (NFR23)
    payload = Column(JSON, nullable=True)
    phase = Column(String(32), nullable=True, index=True)  # study phase (Story 6.5)
    group = Column(String(32), nullable=True, index=True)  # A/B cohort (Story 6.5)
    # Content coordinates (migration 021). Where in the course this event happened.
    course_id = Column(String(64), nullable=True, index=True)
    section_id = Column(String(64), nullable=True, index=True)
    block_id = Column(String(64), nullable=True, index=True)
