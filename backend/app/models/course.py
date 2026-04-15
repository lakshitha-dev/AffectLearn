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


class Course(BaseModel):
    __tablename__ = "courses"

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    estimated_duration_minutes = Column(Integer, nullable=True)
    is_published = Column(Boolean, nullable=False, default=False)

    modules = relationship("Module", back_populates="course", cascade="all, delete-orphan", order_by="Module.sort_order")


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


class ContentBlock(BaseModel):
    __tablename__ = "content_blocks"
    __table_args__ = (
        UniqueConstraint("section_id", "sort_order", name="uq_content_blocks_section_sort"),
    )

    block_type = Column(Enum(BlockType, native_enum=False), nullable=False)
    content = Column(JSON, nullable=False)
    sort_order = Column(Integer, nullable=False)
    variant_key = Column(String(50), nullable=False, default="original")
    variant_group = Column(UUID(as_uuid=True), nullable=False, default=uuid_mod.uuid4)
    section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id", ondelete="CASCADE"), nullable=False, index=True)

    section = relationship("Section", back_populates="content_blocks")
