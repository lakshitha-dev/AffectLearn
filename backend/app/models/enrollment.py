from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Enrollment(BaseModel):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_enrollment_user_course"),
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id = Column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    enrolled_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    progress_percentage = Column(Float, nullable=False, default=0.0)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="active")

    user = relationship("User", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")
    section_progress = relationship(
        "SectionProgress", back_populates="enrollment", cascade="all, delete-orphan"
    )
