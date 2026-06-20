"""Add time_spent_seconds and affect_states to section_progress

Revision ID: 017
Revises: 016
Create Date: 2026-06-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "section_progress",
        sa.Column("time_spent_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "section_progress",
        sa.Column("affect_states", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("section_progress", "affect_states")
    op.drop_column("section_progress", "time_spent_seconds")
