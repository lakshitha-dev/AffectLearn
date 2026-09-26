import enum
import uuid as uuid_mod

from sqlalchemy import (
    Boolean,
    Column,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class BlockType(enum.Enum):
    text = "text"
    code = "code"
    image = "image"
    callout = "callout"
    exercise = "exercise"
    quiz = "quiz"
    # Comparison tables. Stored like every other type: `block_type` is a plain varchar(20) with
    # no CHECK constraint (migration 005 created it as `sa.String(20)` despite the Enum here), so
    # adding a value needs no migration.
    table = "table"


class Course(BaseModel):
    __tablename__ = "courses"

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    estimated_duration_minutes = Column(Integer, nullable=True)
    is_published = Column(Boolean, nullable=False, default=False)
    learning_objectives = Column(Text, nullable=True)
    #: A seeded demonstration course (migration 029). Never listed to a real learner.
    is_demo = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    #: The designer who created this course (migration 024).
    #:
    #: Until this existed, `require_role(course_designer, admin)` was the ONLY guard on every
    #: content mutation, so any designer could edit or DELETE any course — including the seeded
    #: pilot courses a study depends on.
    #:
    #: NULL means SYSTEM-OWNED: courses seeded by `seed_courses.py` have no creating user, and
    #: every course that predates this column is in the same position. Those are admin-only to
    #: edit, which is the conservative reading and the one that protects the pilot content.
    #:
    #: ON DELETE SET NULL rather than CASCADE: removing a designer's account must not delete the
    #: courses they wrote, and the content reverting to system-owned is the right outcome.
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    #: The snapshot taken the last time this course was published (migration 025).
    #:
    #: Null means never published. Learners are still served the LIVE tree, not this snapshot —
    #: see `models/content_version.py` for why that is deliberate. This exists so a measurement
    #: can be checked against the content it was actually taken on.
    #:
    #: `use_alter` because the dependency is circular: a version points at its course, and the
    #: course points back at its current version. Without it, alembic and `create_all` cannot
    #: order the two CREATE TABLE statements.
    published_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "content_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_courses_published_version",
        ),
        nullable=True,
    )

    modules = relationship("Module", back_populates="course", cascade="all, delete-orphan", order_by="Module.sort_order")
    enrollments = relationship("Enrollment", back_populates="course", cascade="all, delete-orphan")
    # `foreign_keys` is required because there are TWO foreign keys between these tables: a
    # version points at its course, and the course points back at its current version. Without
    # it SQLAlchemy cannot tell which one defines the collection.
    versions = relationship(
        "ContentVersion",
        back_populates="course",
        cascade="all, delete-orphan",
        foreign_keys="ContentVersion.course_id",
        order_by="ContentVersion.version_number",
    )


class Module(BaseModel):
    __tablename__ = "modules"
    __table_args__ = (
        UniqueConstraint("course_id", "sort_order", name="uq_modules_course_sort"),
    )

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)

    course = relationship("Course", back_populates="modules")
    lessons = relationship("Lesson", back_populates="module", cascade="all, delete-orphan", order_by="Lesson.sort_order")


class Lesson(BaseModel):
    __tablename__ = "lessons"
    __table_args__ = (
        UniqueConstraint("module_id", "sort_order", name="uq_lessons_module_sort"),
    )

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False)
    module_id = Column(UUID(as_uuid=True), ForeignKey("modules.id", ondelete="CASCADE"), nullable=False, index=True)

    module = relationship("Module", back_populates="lessons")
    sections = relationship("Section", back_populates="lesson", cascade="all, delete-orphan", order_by="Section.sort_order")


class Section(BaseModel):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("lesson_id", "sort_order", name="uq_sections_lesson_sort"),
    )

    title = Column(String(200), nullable=False)
    sort_order = Column(Integer, nullable=False)
    estimated_duration_minutes = Column(Integer, nullable=True, default=5)
    lesson_id = Column(UUID(as_uuid=True), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)

    lesson = relationship("Lesson", back_populates="sections")
    content_blocks = relationship("ContentBlock", back_populates="section", cascade="all, delete-orphan", order_by="ContentBlock.sort_order")
    user_progress = relationship("SectionProgress", back_populates="section", cascade="all, delete-orphan")


class ContentBlock(BaseModel):
    __tablename__ = "content_blocks"
    __table_args__ = (
        # Position is unique WITHIN A VARIANT TRACK, not within the section.
        #
        # A variant is a substitute for the block it alternates for, standing in the same place
        # in the same section — so it legitimately carries the same `sort_order`. The original
        # two-column constraint made that impossible and would have forced authored variants to
        # be parked at meaningless positions past the end of the section.
        UniqueConstraint(
            "section_id",
            "variant_key",
            "sort_order",
            name="uq_content_blocks_section_variant_sort",
        ),
    )

    block_type = Column(Enum(BlockType, native_enum=False), nullable=False)
    content = Column(JSON, nullable=False)
    sort_order = Column(Integer, nullable=False)
    variant_key = Column(String(50), nullable=False, default="original")
    variant_group = Column(UUID(as_uuid=True), nullable=False, default=uuid_mod.uuid4)
    section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id", ondelete="CASCADE"), nullable=False, index=True)

    section = relationship("Section", back_populates="content_blocks")
