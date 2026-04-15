"""Rename role enum value designer to course_designer

Revision ID: 004
Revises: 003
Create Date: 2026-04-03

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE role RENAME VALUE 'designer' TO 'course_designer'")


def downgrade() -> None:
    op.execute("ALTER TYPE role RENAME VALUE 'course_designer' TO 'designer'")
