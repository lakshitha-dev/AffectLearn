import enum

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, String
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
    # WHAT WAS CONSENTED TO, AND UNDER WHICH TEXT (migration 032).
    #
    # `consent_given_at` alone recorded that a box was ticked, not what it said or what it covered.
    # `consent_version` names the consent text the learner saw; `consent_scopes` records the
    # optional parts separately (see `services/consent.py` for the scope names). Webcam consent is
    # `webcam_enabled` itself -- the learner's camera choice -- so the two can never disagree.
    # `consent_withdrawn_at` stops all capture at once without deleting the account, so a
    # participant can stop the study first and decide about their data afterwards.
    consent_version = Column(String(32), nullable=True)
    consent_scopes = Column(JSON, nullable=True)
    consent_withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    #: A seeded demonstration account (migration 029, `app/db/seed_demo.py`). Excluded from every
    #: research surface — see `services/demo_scope.py`.
    is_demo = Column(Boolean, nullable=False, default=False, server_default="false", index=True)

    enrollments = relationship(
        "Enrollment", back_populates="user", cascade="all, delete-orphan"
    )
    section_progress = relationship(
        "SectionProgress", back_populates="user", cascade="all, delete-orphan"
    )
