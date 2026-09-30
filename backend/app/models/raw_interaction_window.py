"""The raw timed events of one 30-second behavioural window, for learners who opted in (migration 033).

WHY THIS EXISTS

The behavioural channel keeps only what the model consumes: the (30 x 16) feature window in
`behavioral_affect_detected.payload.features`. The raw events it was computed from -- pointer
positions, clicks and what was clicked, scrolls, key CATEGORIES with their timing -- were discarded
after each cycle. On this platform that model almost never reaches its confidence floor, and the
two corpora it was trained on are proxies, so the pilot's own raw interaction record is the only
material from which a better feature set could be derived for these learners.

WHAT IS AND IS NOT HERE

Exactly what the browser sent in `behavioral_window.data`: `events` (the model's input stream),
`ui_events` (hover dwell and clipboard actions -- context, never model input), the viewport the
coordinates refer to, and identifiers. Never key values, typed text, clipboard content or anything
from a password or `data-private` field: the browser does not capture them (see
`frontend/src/hooks/use-behavioral-signals.ts`), so they cannot be stored.

CONSENT AND ERASURE

Written only for a learner whose `consent_scopes.raw_interaction` is true (`services/consent.py`).
The foreign key cascades, so erasing the learner removes these rows with the account; a separate
retention period can purge them earlier than the derived features.
"""

from sqlalchemy import JSON, BigInteger, Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import BaseModel


class RawInteractionWindow(BaseModel):
    __tablename__ = "raw_interaction_windows"

    learner_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    session_id = Column(String(64), nullable=True, index=True)
    #: One id per lesson-page mount. Cycle numbers restart on every page, so this is what tells two
    #: visits to a page apart.
    page_instance_id = Column(String(64), nullable=True, index=True)
    cycle_number = Column(Integer, nullable=False, default=0)
    #: Joins this window to its `behavioral_affect_detected` research event.
    decision_id = Column(String(36), nullable=True, index=True)
    section_id = Column(String(64), nullable=True, index=True)
    capture_started_at_wall = Column(BigInteger, nullable=True)   # unix ms, browser clock
    capture_ended_at_wall = Column(BigInteger, nullable=True)
    received_at_ms = Column(BigInteger, nullable=True)            # unix ms, server clock
    schema_version = Column(Integer, nullable=True)
    viewport = Column(JSON, nullable=True)
    events = Column(JSON, nullable=False, default=list)
    ui_events = Column(JSON, nullable=True)
    dropped_events = Column(Integer, nullable=False, default=0)
    #: Set when the browser marked the window as cut short. The deployed client does not send
    #: partial windows; the column exists so one would never be mistaken for a full 30 s.
    partial = Column(Boolean, nullable=False, default=False)
