"""Create survey_responses table (Story 6.4)

Post-study satisfaction survey data: one row per user account holding the four AC-dimension
Likert answers (perceived adaptation quality, learning experience, willingness to continue,
overall satisfaction) as a structured `responses` JSON blob, linked to `user_id` (unique →
one response per learner; re-submit is an idempotent upsert). Pilot-blocking, so it ships as a
real migration matching the 001-014 chain. Mirrors 014 (`questionnaire_responses`) exactly.

Revision ID: 015
Revises: 014
Create Date: 2026-06-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "survey_responses",
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
        sa.Column("responses", sa.JSON, nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_survey_responses_user_id",
        "survey_responses",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_survey_responses_user_id", table_name="survey_responses")
    op.drop_table("survey_responses")
