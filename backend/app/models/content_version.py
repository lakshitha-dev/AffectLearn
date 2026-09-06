"""An immutable snapshot of a course's content, taken at publish (migration 025).

THE PROBLEM

Course content is mutated in place. There is no history, and `is_published` is a single boolean,
so a designer fixing a typo and a designer rewriting a section are indistinguishable afterwards —
and both silently change the meaning of every measurement already attached to that section.

That matters more here than in an ordinary LMS. The affect heatmap says "learners were confused
in section X". If section X has been rewritten since, the figure describes content that no longer
exists, and nothing in the database says so. During a study it is worse than useless: it is a
number that looks current and is not.

WHAT A VERSION IS

The whole module/lesson/section/block tree as it stood when publish was pressed, stored as JSON.
Not a diff — a diff is only meaningful against a base that is itself immutable, and the live tree
is not. JSON rather than shadow tables because a snapshot is never queried by structure, only read
back whole, and shadow tables would double every schema change forever.

WHAT THIS DELIBERATELY DOES NOT DO

Learners are still served the LIVE tree, not the published snapshot. Serving from a snapshot is a
larger product change — it needs a draft/preview story, and it changes the read path every learner
depends on — and doing it as a side effect of an analytics fix would be the wrong way round. What
this gives is ATTRIBUTION: a record of what the content was, and which version a learner's
progress belongs to, so a figure can be checked against the material it was measured on.
"""

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class ContentVersion(BaseModel):
    __tablename__ = "content_versions"
    __table_args__ = (
        UniqueConstraint("course_id", "version_number", name="uq_content_version_number"),
    )

    course_id = Column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: 1-based, per course. A snapshot of a course that no longer exists has nothing to describe,
    #: which is why this cascades where the research record does not.
    version_number = Column(Integer, nullable=False)
    #: The full content tree. See the module docstring for why JSON rather than shadow tables.
    snapshot = Column(JSON, nullable=False)
    published_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    #: SET NULL: a designer leaving must not erase the record of what was published.
    published_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    course = relationship("Course", back_populates="versions", foreign_keys=[course_id])
