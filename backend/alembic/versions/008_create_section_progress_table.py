"""Create section_progress table

Revision ID: 008
Revises: 007
Create Date: 2026-05-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "section_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "section_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "enrollment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enrollments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "section_id", name="uq_section_progress_user_section"
        ),
    )
    op.create_index(
        "ix_section_progress_user_id", "section_progress", ["user_id"]
    )
    op.create_index(
        "ix_section_progress_section_id", "section_progress", ["section_id"]
    )
    op.create_index(
        "ix_section_progress_enrollment_id", "section_progress", ["enrollment_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_section_progress_enrollment_id", table_name="section_progress"
    )
    op.drop_index(
        "ix_section_progress_section_id", table_name="section_progress"
    )
    op.drop_index("ix_section_progress_user_id", table_name="section_progress")
    op.drop_table("section_progress")
