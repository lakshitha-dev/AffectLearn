"""Keep the raw timed events of a behavioural window, for learners who opted in

The behavioural channel stored only the features its model consumes and discarded the raw events
they were computed from. That model rarely reaches its floor on this platform and was trained on
proxy corpora, so the pilot's own raw interaction record is the material a better feature set would
have to come from. One row per 30 s window, written only under the `raw_interaction` consent scope
(migration 032) and cascading with the learner's account.

Revision ID: 033
Revises: 032
Create Date: 2026-09-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "raw_interaction_windows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("learner_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("page_instance_id", sa.String(64), nullable=True),
        sa.Column("cycle_number", sa.Integer, nullable=False, server_default="0"),
        sa.Column("decision_id", sa.String(36), nullable=True),
        sa.Column("section_id", sa.String(64), nullable=True),
        sa.Column("capture_started_at_wall", sa.BigInteger, nullable=True),
        sa.Column("capture_ended_at_wall", sa.BigInteger, nullable=True),
        sa.Column("received_at_ms", sa.BigInteger, nullable=True),
        sa.Column("schema_version", sa.Integer, nullable=True),
        sa.Column("viewport", sa.JSON, nullable=True),
        sa.Column("events", sa.JSON, nullable=False),
        sa.Column("ui_events", sa.JSON, nullable=True),
        sa.Column("dropped_events", sa.Integer, nullable=False, server_default="0"),
        sa.Column("partial", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_raw_interaction_windows_learner_id", "raw_interaction_windows",
                    ["learner_id"])
    op.create_index("ix_raw_interaction_windows_session_id", "raw_interaction_windows",
                    ["session_id"])
    op.create_index("ix_raw_interaction_windows_page_instance_id", "raw_interaction_windows",
                    ["page_instance_id"])
    op.create_index("ix_raw_interaction_windows_decision_id", "raw_interaction_windows",
                    ["decision_id"])
    op.create_index("ix_raw_interaction_windows_section_id", "raw_interaction_windows",
                    ["section_id"])


def downgrade() -> None:
    op.drop_table("raw_interaction_windows")
