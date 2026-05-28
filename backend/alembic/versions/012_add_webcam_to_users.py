"""Add webcam_enabled to users

Revision ID: 012
Revises: 011
Create Date: 2026-05-08
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("webcam_enabled", sa.Boolean, nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("users", "webcam_enabled")
