"""Initial base model

Revision ID: 001
Revises:
Create Date: 2026-03-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Base model establishes UUID primary key, created_at, updated_at pattern
    # Concrete tables will be created in subsequent migrations
    pass


def downgrade() -> None:
    pass
