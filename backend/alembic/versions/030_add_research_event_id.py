"""Give every research event an idempotency key

The research worker drains the Redis stream into Postgres. Its read position lived only in
process memory and started at "0" on every boot, so each API restart re-read the whole stream
(up to ~100k entries) and inserted all of it again. Nothing in `research_events` could tell the
copies apart: there was no unique key, and the per-session sequence number restarted as well.

`event_id` is a UUID assigned once, at emit. The worker now skips any event whose id is already
stored, so re-reading a batch is harmless. The column is nullable because historical rows have no
id; a unique index admits any number of NULLs on both Postgres and SQLite.

Revision ID: 030
Revises: 029
Create Date: 2026-09-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("research_events", sa.Column("event_id", sa.String(36), nullable=True))
    op.create_index(
        "ix_research_events_event_id", "research_events", ["event_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_research_events_event_id", table_name="research_events")
    op.drop_column("research_events", "event_id")
