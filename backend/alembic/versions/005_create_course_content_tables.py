"""Create course content tables

Revision ID: 005
Revises: 004
Create Date: 2026-04-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # courses
    op.create_table(
        "courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("estimated_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # modules
    op.create_table(
        "modules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("course_id", "sort_order", name="uq_modules_course_sort"),
    )
    op.create_index("ix_modules_course_id", "modules", ["course_id"])

    # lessons
    op.create_table(
        "lessons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("modules.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("module_id", "sort_order", name="uq_lessons_module_sort"),
    )
    op.create_index("ix_lessons_module_id", "lessons", ["module_id"])

    # sections
    op.create_table(
        "sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("estimated_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("lesson_id", "sort_order", name="uq_sections_lesson_sort"),
    )
    op.create_index("ix_sections_lesson_id", "sections", ["lesson_id"])

    # content_blocks (block_type stored as VARCHAR via native_enum=False in model)
    op.create_table(
        "content_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("block_type", sa.String(20), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("variant_key", sa.String(50), nullable=False, server_default="original"),
        sa.Column("variant_group", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sections.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("section_id", "sort_order", name="uq_content_blocks_section_sort"),
    )
    op.create_index("ix_content_blocks_section_id", "content_blocks", ["section_id"])


def downgrade() -> None:
    op.drop_index("ix_content_blocks_section_id", table_name="content_blocks")
    op.drop_table("content_blocks")
    op.drop_index("ix_sections_lesson_id", table_name="sections")
    op.drop_table("sections")
    op.drop_index("ix_lessons_module_id", table_name="lessons")
    op.drop_table("lessons")
    op.drop_index("ix_modules_course_id", table_name="modules")
    op.drop_table("modules")
    op.drop_table("courses")
