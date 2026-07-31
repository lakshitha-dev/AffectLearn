import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, String
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Role(enum.Enum):
    learner = "learner"
    course_designer = "course_designer"
    admin = "admin"


class User(BaseModel):
    __tablename__ = "users"

    email_address = Column(String(320), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    age_range = Column(String(20), nullable=True)
    degree_program = Column(String(200), nullable=True)
    role = Column(Enum(Role), nullable=False, default=Role.learner)
    is_active = Column(Boolean, nullable=False, default=True)
    # New self-registered accounts start unverified and cannot log in until they confirm
    # their email. Seeded/pre-existing accounts are backfilled to True (migration 018).
    email_verified = Column(Boolean, nullable=False, default=False)
    consent_given_at = Column(DateTime(timezone=True), nullable=True)
    webcam_enabled = Column(Boolean, nullable=False, default=False)
    # Last successful login timestamp; surfaced in the admin user table (Story 8.1).
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    enrollments = relationship(
        "Enrollment", back_populates="user", cascade="all, delete-orphan"
    )
    section_progress = relationship(
        "SectionProgress", back_populates="user", cascade="all, delete-orphan"
    )
