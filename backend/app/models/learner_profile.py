"""Cold (durable) learner-profile store (Story 4.5).

One row per learner holding the agent loop's dynamic profile as JSON. The hot copy lives
in Redis; this is the cross-session source of truth (FR31). A normalized schema can replace
the JSON blob later without changing the profile_service interface.

NOTE: the alembic migration for this table is a deploy forward-item; the test suite builds
it via `Base.metadata.create_all`.
"""

from sqlalchemy import JSON, Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import BaseModel


class LearnerProfile(BaseModel):
    __tablename__ = "learner_profiles"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    profile = Column(JSON, nullable=False, default=dict)
