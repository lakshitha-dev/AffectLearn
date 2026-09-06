"""Create assistance_events: the queryable ledger of help offered to learners

`research_events` already records the intervention chain, including the hint text and the
strategist's reason. That is the right home for it as research data and it stays. It is the wrong
home for a product feature: it arrives on a best-effort Redis path that degrades to a log line
when the cache is down, one intervention is spread across four rows keyed by session and cycle,
everything interesting lives in an unindexed JSON payload, and the outcome is not in it at all --
the answer a learner gives next arrives minutes later over REST, not on the WebSocket cycle.

This table is the projection you can serve a page from: one row per intervention, written at
delivery, updated when the learner responds and again when they next answer a question.

Content foreign keys are ON DELETE SET NULL rather than CASCADE. A designer deleting a section
must not erase the evidence that learners needed help in it; the row survives and stops pointing
at a ghost.

Revision ID: 023
Revises: 022
Create Date: 2026-09-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assistance_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),

        sa.Column("adaptation_id", sa.String(length=64), nullable=False),
        sa.Column("learner_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("cycle_number", sa.Integer(), nullable=False, server_default="0"),

        sa.Column("course_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("courses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("section_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sections.id", ondelete="SET NULL"), nullable=True),

        sa.Column("affect_state", sa.String(length=16), nullable=True),
        sa.Column("affect_source", sa.String(length=32), nullable=True),
        sa.Column("affect_confidence", sa.Float(), nullable=True),
        sa.Column("gate_reason", sa.String(length=32), nullable=True),

        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("urgency", sa.String(length=16), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),

        sa.Column("hint_text", sa.Text(), nullable=True),
        sa.Column("variant", sa.String(length=50), nullable=True),
        sa.Column("generated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fallback_reason", sa.String(length=64), nullable=True),

        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_failed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("interaction", sa.String(length=16), nullable=True),
        sa.Column("interacted_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("outcome_attempt_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("quiz_attempts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("outcome_is_correct", sa.Boolean(), nullable=True),
        sa.Column("outcome_resolved_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("phase", sa.String(length=32), nullable=True),
        sa.Column("group", sa.String(length=32), nullable=True),
    )

    # Unique: `adaptation_id` is the key the client echoes back on both the interaction and the
    # following quiz attempt. A duplicate would split one intervention's response across two rows.
    op.create_index(
        "ix_assistance_events_adaptation_id", "assistance_events",
        ["adaptation_id"], unique=True,
    )
    op.create_index("ix_assistance_events_learner_id", "assistance_events", ["learner_id"])
    op.create_index("ix_assistance_events_session_id", "assistance_events", ["session_id"])
    op.create_index("ix_assistance_events_course_id", "assistance_events", ["course_id"])
    op.create_index("ix_assistance_events_section_id", "assistance_events", ["section_id"])
    op.create_index("ix_assistance_events_interaction", "assistance_events", ["interaction"])
    op.create_index("ix_assistance_events_phase", "assistance_events", ["phase"])
    op.create_index("ix_assistance_events_group", "assistance_events", ["group"])
    # "This learner's help, newest first" is the learner-facing read; "help in this section" is
    # the designer one. Both sort by time, so both want the composite rather than a bare index.
    op.create_index(
        "ix_assistance_events_learner_created",
        "assistance_events", ["learner_id", "created_at"],
    )
    op.create_index(
        "ix_assistance_events_section_created",
        "assistance_events", ["section_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_assistance_events_section_created", table_name="assistance_events")
    op.drop_index("ix_assistance_events_learner_created", table_name="assistance_events")
    op.drop_index("ix_assistance_events_group", table_name="assistance_events")
    op.drop_index("ix_assistance_events_phase", table_name="assistance_events")
    op.drop_index("ix_assistance_events_interaction", table_name="assistance_events")
    op.drop_index("ix_assistance_events_section_id", table_name="assistance_events")
    op.drop_index("ix_assistance_events_course_id", table_name="assistance_events")
    op.drop_index("ix_assistance_events_session_id", table_name="assistance_events")
    op.drop_index("ix_assistance_events_learner_id", table_name="assistance_events")
    op.drop_index("ix_assistance_events_adaptation_id", table_name="assistance_events")
    op.drop_table("assistance_events")
