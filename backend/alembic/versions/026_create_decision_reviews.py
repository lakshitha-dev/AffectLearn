"""Create decision_reviews — educator ratings of pedagogical decisions

The pedagogical agent's reported quality is Cohen's kappa 0.79 against the rule policy it was
trained on. That measures fidelity, not pedagogy: an agent faithfully reproducing a bad policy
scores identically. No qualified educator has ever been asked whether the decisions are good.

The thesis names this the highest-value outstanding work per hour invested and notes it does not
depend on the pilot. This table is where those ratings land.

One row per (reviewer, decision), enforced. Ratings are kept per reviewer rather than averaged,
because inter-rater agreement is the point — an average discards exactly the disagreement that
says whether the rubric means the same thing to two people.

Revision ID: 026
Revises: 025
Create Date: 2026-09-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decision_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("assistance_event_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("assistance_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ratings", sa.JSON(), nullable=False),
        sa.Column("would_make_same_call", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("rubric_version", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("assistance_event_id", "reviewer_id", name="uq_decision_review"),
    )
    op.create_index(
        "ix_decision_reviews_assistance_event_id", "decision_reviews", ["assistance_event_id"]
    )
    op.create_index("ix_decision_reviews_reviewer_id", "decision_reviews", ["reviewer_id"])
    op.create_index("ix_decision_reviews_submitted_at", "decision_reviews", ["submitted_at"])


def downgrade() -> None:
    op.drop_index("ix_decision_reviews_submitted_at", table_name="decision_reviews")
    op.drop_index("ix_decision_reviews_reviewer_id", table_name="decision_reviews")
    op.drop_index("ix_decision_reviews_assistance_event_id", table_name="decision_reviews")
    op.drop_table("decision_reviews")
