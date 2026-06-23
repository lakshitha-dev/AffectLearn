"""Add email_verified to users

Revision ID: 018
Revises: 017
Create Date: 2026-06-23
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean, nullable=False, server_default="false"),
    )
    # Backfill: every pre-existing account (seeded + already-registered users) is treated
    # as verified so the new login gate never locks anyone out. Only accounts created
    # after this migration start unverified.
    op.execute("UPDATE users SET email_verified = true")


def downgrade() -> None:
    op.drop_column("users", "email_verified")
