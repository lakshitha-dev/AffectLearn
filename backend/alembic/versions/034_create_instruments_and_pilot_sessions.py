"""Questionnaire administrations and facilitator sitting records for the pilot

`instrument_responses` holds one row per administration of a questionnaire (lesson feedback after
every lesson, SUS and UEQ-S at the end), with its version, context and whether it was skipped; the
existing one-row-per-account survey tables cannot hold repeated administrations.

`pilot_sessions` holds one row per participant sitting in the in-person pilot: participant code,
arm, protocol and consent versions, configuration version at the start, device, start and end, the
reason it ended and any protocol deviation. No names.

Revision ID: 034
Revises: 033
Create Date: 2026-09-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instrument_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instrument", sa.String(32), nullable=False),
        sa.Column("instrument_version", sa.String(16), nullable=False),
        sa.Column("context", sa.JSON, nullable=True),
        sa.Column("responses", sa.JSON, nullable=False),
        sa.Column("skipped", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("shown_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )
    op.create_index("ix_instrument_responses_user_id", "instrument_responses", ["user_id"])
    op.create_index("ix_instrument_responses_instrument", "instrument_responses", ["instrument"])

    op.create_table(
        "pilot_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("participant_code", sa.String(16), nullable=False),
        sa.Column("group", sa.String(32), nullable=True),
        sa.Column("phase", sa.String(32), nullable=True),
        sa.Column("protocol_version", sa.String(32), nullable=True),
        sa.Column("consent_version", sa.String(32), nullable=True),
        sa.Column("config_version_at_start", sa.Integer, nullable=True),
        sa.Column("device", sa.JSON, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(16), nullable=True),
        sa.Column("deviation_notes", sa.Text, nullable=True),
    )
    op.create_index("ix_pilot_sessions_user_id", "pilot_sessions", ["user_id"])
    op.create_index("ix_pilot_sessions_participant_code", "pilot_sessions", ["participant_code"])


def downgrade() -> None:
    op.drop_table("pilot_sessions")
    op.drop_table("instrument_responses")
