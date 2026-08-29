"""Create learner_profiles table

The `LearnerProfile` model has existed since the profiler was written, but no migration was ever
generated for it. Verified against production on 2026-08-29: the table did not exist and
`alembic_version` was at 019.

The effect was silent, because the Learner Profiler degrades rather than fails. Both of its cold-store
calls sit inside bare `except` blocks (`learner_profiler.py` — `profile_service.load_or_init` on load,
`persist_cold` every PROFILE_COLD_PERSIST_EVERY cycles), so each raised `UndefinedTableError`, logged
`profile_cold_load_failed` / `profile_cold_persist_failed`, and the cycle carried on. Production
telemetry showed profile load `source` was **100% redis** across 400 consecutive cycles — Postgres had
never once served a profile.

Consequence: the learner profile lived only in Redis. A restart or key eviction permanently destroyed
that learner's `affect_history`, `topic_mastery`, `format_preferences` and adaptation cooldown state —
unrecoverable participant data on a research platform.

No application code changes with this migration: the model and `profile_service` were always correct.
Only the table was missing.

Revision ID: 020
Revises: 019
Create Date: 2026-08-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learner_profiles",
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
        # JSON rather than JSONB to match the model's `Column(JSON, ...)`. The profile is read and
        # written whole, never queried by key, so JSONB's indexing would buy nothing.
        sa.Column("profile", sa.JSON(), nullable=False),
    )
    # UNIQUE, not merely indexed: the model declares `unique=True`, and `profile_service` relies on
    # one row per learner — a duplicate would make "which profile is current?" ambiguous.
    op.create_index(
        "ix_learner_profiles_user_id", "learner_profiles", ["user_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_learner_profiles_user_id", table_name="learner_profiles")
    op.drop_table("learner_profiles")
