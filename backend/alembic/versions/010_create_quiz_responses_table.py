"""Create quiz_responses table

Revision ID: 010
Revises: 009
Create Date: 2026-05-08
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quiz_responses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_block_id", UUID(as_uuid=True), sa.ForeignKey("content_blocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("selected_answers", sa.JSON, nullable=False),
        sa.Column("is_correct", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "content_block_id", name="uq_quiz_response_user_block"),
    )
    op.create_index("ix_quiz_responses_user_id", "quiz_responses", ["user_id"])
    op.create_index("ix_quiz_responses_block_id", "quiz_responses", ["content_block_id"])


def downgrade() -> None:
    op.drop_table("quiz_responses")
