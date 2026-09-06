"""Create content_versions and link courses / section_progress to them

Course content is mutated in place with no history, so a designer rewriting a section silently
changes the meaning of every measurement already attached to it. The affect heatmap saying
"learners were confused in section X" cannot be distinguished from "learners were confused in a
section that has since been rewritten", and nothing in the database records which it is.

A version is the whole module/lesson/section/block tree as it stood at publish, stored as JSON.
Not a diff, because a diff is only meaningful against an immutable base and the live tree is not
one. JSON rather than shadow tables because a snapshot is read back whole and never queried by
structure, and shadow tables would double every future schema change.

`courses.published_version_id` and `content_versions.course_id` point at each other, so the FK
from courses is created SEPARATELY after both tables exist — a circular dependency cannot be
satisfied by two CREATE TABLE statements in either order.

Learners are still served the LIVE tree. Serving from the snapshot needs a draft/preview story
and changes the read path every learner depends on; doing that as a side effect of an analytics
fix would be the wrong way round. What this migration delivers is attribution.

Revision ID: 025
Revises: 024
Create Date: 2026-09-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("published_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("course_id", "version_number", name="uq_content_version_number"),
    )
    op.create_index("ix_content_versions_course_id", "content_versions", ["course_id"])
    op.create_index("ix_content_versions_published_at", "content_versions", ["published_at"])

    # Created after both tables exist — see the module docstring on the circular dependency.
    op.add_column(
        "courses",
        sa.Column("published_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_courses_published_version",
        "courses",
        "content_versions",
        ["published_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "section_progress",
        sa.Column("content_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_section_progress_content_version",
        "section_progress",
        "content_versions",
        ["content_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_section_progress_content_version_id",
        "section_progress",
        ["content_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_section_progress_content_version_id", table_name="section_progress")
    op.drop_constraint(
        "fk_section_progress_content_version", "section_progress", type_="foreignkey"
    )
    op.drop_column("section_progress", "content_version_id")

    op.drop_constraint("fk_courses_published_version", "courses", type_="foreignkey")
    op.drop_column("courses", "published_version_id")

    op.drop_index("ix_content_versions_published_at", table_name="content_versions")
    op.drop_index("ix_content_versions_course_id", table_name="content_versions")
    op.drop_table("content_versions")
