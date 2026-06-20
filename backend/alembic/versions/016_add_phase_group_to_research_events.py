"""Create research_events table + add phase/group columns (Story 6.5)

Story 4.7 hardened the research-event pipeline (emit → Redis Stream → worker → PostgreSQL)
but deliberately deferred the `research_events` DDL as a "deploy forward-item" — through
Story 6.4's `015` no migration creates the table (tests build it via `Base.metadata.create_all`).
Story 6.5 makes the dataset queryable/exportable, so this migration is the FIRST to materialise
`research_events` for real deployments, mirroring `app.models.research_event.ResearchEvent` and
4.7's indexes, THEN adds the new nullable, indexed `phase` and `group` columns so the dataset is
filterable by study phase (Phase A / Phase B) and A/B cohort.

Revision ID: 016
Revises: 015
Create Date: 2026-06-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Materialise the research_events table (4.7 deferred its DDL). Mirrors the model +
    #    4.7's index set (event_type / learner_id / session_id).
    op.create_table(
        "research_events",
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
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("learner_id", sa.String(length=64), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("cycle_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        # Story 6.5: filterable study phase + A/B cohort columns.
        sa.Column("phase", sa.String(length=32), nullable=True),
        sa.Column("group", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_research_events_event_type", "research_events", ["event_type"]
    )
    op.create_index(
        "ix_research_events_learner_id", "research_events", ["learner_id"]
    )
    op.create_index(
        "ix_research_events_session_id", "research_events", ["session_id"]
    )
    # Story 6.5 indexes for phase/group filtering.
    op.create_index("ix_research_events_phase", "research_events", ["phase"])
    op.create_index("ix_research_events_group", "research_events", ["group"])


def downgrade() -> None:
    op.drop_index("ix_research_events_group", table_name="research_events")
    op.drop_index("ix_research_events_phase", table_name="research_events")
    op.drop_index("ix_research_events_session_id", table_name="research_events")
    op.drop_index("ix_research_events_learner_id", table_name="research_events")
    op.drop_index("ix_research_events_event_type", table_name="research_events")
    op.drop_table("research_events")
