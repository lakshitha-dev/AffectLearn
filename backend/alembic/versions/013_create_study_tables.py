"""Create study_groups and study_phase tables (Story 6.1)

Pilot-study infrastructure: account-level A/B group assignment (immutable once locked)
and the global study-phase singleton. Both are pilot-blocking, so they ship as a real
migration (matching the 001-012 chain) rather than a deploy forward-item.

Revision ID: 013
Revises: 012
Create Date: 2026-06-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "study_groups",
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
        sa.Column("group", sa.String(length=16), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_study_groups_user_id", "study_groups", ["user_id"], unique=True
    )

    op.create_table(
        "study_phase",
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
        sa.Column("phase", sa.String(length=16), nullable=False, server_default="phase_a"),
        sa.Column("transitioned_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("study_phase")
    op.drop_index("ix_study_groups_user_id", table_name="study_groups")
    op.drop_table("study_groups")
