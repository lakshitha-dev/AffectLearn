"""Durable research event store (Story 4.7).

Every affect classification, agent decision, and interaction is persisted here for thesis
analysis. `sequence_number` is monotonic per `session_id` so dropped events are detectable
(NFR23). Populated by the background worker draining the Redis Stream.

NOTE: the alembic migration for this table is a deploy forward-item; tests build it via
`Base.metadata.create_all`.
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
