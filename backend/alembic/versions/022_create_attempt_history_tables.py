"""Attempt history: quiz_attempts, section_visits, and assessment attempt ordinals

Three durable additions that record what learners DID, not only where they ended up.

`quiz_attempts` exists because `quiz_responses` is UNIQUE(user_id, content_block_id) and its
route returns the existing row on a repeat, so the first answer wins and every later one is
discarded. A learner who answers wrongly, is helped, and then answers correctly leaves a record
saying only "wrong". Attempt counts, repeated mistakes, per-attempt timing and "did they succeed
after being helped" were therefore all unrecoverable from the durable tables. `quiz_responses` is
deliberately KEPT and UNCHANGED: it remains the per-block summary `progress_service` counts, and
redefining that metric would silently move every learner's reported accuracy partway through a
study.

`section_visits` exists because `section_progress` is UNIQUE(user_id, section_id) holding one
completion. Revisiting a section is one of the few reliable struggle signals this interface
produces, and a section revisited but never completed currently leaves no trace at all.

`assessment_attempts.attempt_number` exists because the code already reads it. The
`exercise_attempted` research event emits the attempt ordinal via getattr with a default of 0,
and nothing ever assigned it, so every such event recorded a constant zero. `started_at`
accompanies it so time-taken on a pre/post assessment is derivable.

Revision ID: 022
Revises: 021
Create Date: 2026-09-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Columns are written out inline rather than built by a helper: the migration-coverage guard
    # parses these files statically (it cannot run alembic without a database), so a column
    # produced by a function call is invisible to it and the guard would silently cover nothing.
    op.create_table(
        "quiz_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_block_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("content_blocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sections.id", ondelete="CASCADE"), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("selected_answers", sa.JSON(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("assistance_id", sa.String(length=64), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_quiz_attempts_user_id", "quiz_attempts", ["user_id"])
    op.create_index("ix_quiz_attempts_content_block_id", "quiz_attempts", ["content_block_id"])
    op.create_index("ix_quiz_attempts_section_id", "quiz_attempts", ["section_id"])
    op.create_index("ix_quiz_attempts_assistance_id", "quiz_attempts", ["assistance_id"])
    op.create_index("ix_quiz_attempts_submitted_at", "quiz_attempts", ["submitted_at"])
    # The hint-to-outcome query is "this learner's attempts on this block, in order". Without a
    # composite index that is an index scan plus a sort on every read.
    op.create_index(
        "ix_quiz_attempts_user_block_attempt",
        "quiz_attempts",
        ["user_id", "content_block_id", "attempt_number"],
    )

    op.create_table(
        "section_visits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("entered_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("entry_source", sa.String(length=16), nullable=True),
    )
    op.create_index("ix_section_visits_user_id", "section_visits", ["user_id"])
    op.create_index("ix_section_visits_section_id", "section_visits", ["section_id"])
    op.create_index("ix_section_visits_enrollment_id", "section_visits", ["enrollment_id"])
    op.create_index("ix_section_visits_entered_at", "section_visits", ["entered_at"])

    # Existing rows are real attempts, so they backfill to attempt 1 rather than 0. The column
    # stays NOT NULL because every attempt has an ordinal; a nullable one would reintroduce the
    # ambiguity this fixes.
    op.add_column(
        "assessment_attempts",
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "assessment_attempts",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("assessment_attempts", "started_at")
    op.drop_column("assessment_attempts", "attempt_number")

    op.drop_index("ix_section_visits_entered_at", table_name="section_visits")
    op.drop_index("ix_section_visits_enrollment_id", table_name="section_visits")
    op.drop_index("ix_section_visits_section_id", table_name="section_visits")
    op.drop_index("ix_section_visits_user_id", table_name="section_visits")
    op.drop_table("section_visits")

    op.drop_index("ix_quiz_attempts_user_block_attempt", table_name="quiz_attempts")
    op.drop_index("ix_quiz_attempts_submitted_at", table_name="quiz_attempts")
    op.drop_index("ix_quiz_attempts_assistance_id", table_name="quiz_attempts")
    op.drop_index("ix_quiz_attempts_section_id", table_name="quiz_attempts")
    op.drop_index("ix_quiz_attempts_content_block_id", table_name="quiz_attempts")
    op.drop_index("ix_quiz_attempts_user_id", table_name="quiz_attempts")
    op.drop_table("quiz_attempts")
