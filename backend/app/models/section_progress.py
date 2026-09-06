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


class SectionProgress(BaseModel):
    __tablename__ = "section_progress"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "section_id", name="uq_section_progress_user_section"
        ),
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    enrollment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    completed_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Story 4.6 — richer completion record (nullable; back-compatible)
    time_spent_seconds = Column(Integer, nullable=True)
    affect_states = Column(JSON, nullable=True)  # list of affect labels observed in-section
    #: Which published snapshot of the course this completion belongs to (migration 025).
    #:
    #: Without it, "learners were confused in section X" cannot be told apart from "learners were
    #: confused in a section that has since been rewritten". Nullable: completions recorded
    #: before this column, and completions on a course that has never been published, have no
    #: version to point at.
    content_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("content_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    user = relationship("User", back_populates="section_progress")
    section = relationship("Section", back_populates="user_progress")
    enrollment = relationship("Enrollment", back_populates="section_progress")
