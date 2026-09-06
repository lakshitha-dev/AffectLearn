"""Append-only record of every visit to a section (migration 022).

WHY THIS EXISTS

`section_progress` is `UNIQUE(user_id, section_id)` holding one `completed_at` and one
`time_spent_seconds`. It answers "did this learner finish this section" and nothing else. A
learner who reads a section, moves on, comes back confused, and re-reads it leaves exactly the
same row as one who read it once and understood it.

Revisiting is one of the few struggle signals this interface produces reliably.
`section_features` already counts `view_count` and `back_nav_count`, but only from counters the
client sends at COMPLETION -- so a section that is revisited and never completed contributes
nothing, which is precisely the case worth seeing.

WHAT `entry_source` IS FOR

Arriving by "next" is the normal path; arriving by "back" is a learner returning to material
they had left, and "resume" is a new session picking up where the last one stopped. The three
mean different things about the visit and cannot be recovered from timestamps alone.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import BaseModel

#: How a learner arrived at the section. Open vocabulary rather than an enum: a new navigation
#: affordance should not need a migration, and an unrecognised value is still a fact.
ENTRY_SOURCES = ("next", "back", "resume", "direct")


class SectionVisit(BaseModel):
    __tablename__ = "section_visits"

    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    section_id = Column(
        UUID(as_uuid=True), ForeignKey("sections.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    #: Nullable: a learner can open a section of a course they have not enrolled in if a link is
    #: shared, and the visit is still a fact worth recording.
    enrollment_id = Column(
        UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    entered_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    #: Set when the learner navigates away. Null means either "still here" or "the browser was
    #: closed and the closing beacon never arrived" -- the two are indistinguishable, so readers
    #: must treat an open visit as unknown-duration rather than as an infinite one.
    left_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    entry_source = Column(String(16), nullable=True)
