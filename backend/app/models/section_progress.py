from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
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

    user = relationship("User", back_populates="section_progress")
    section = relationship("Section", back_populates="user_progress")
    enrollment = relationship("Enrollment", back_populates="section_progress")
