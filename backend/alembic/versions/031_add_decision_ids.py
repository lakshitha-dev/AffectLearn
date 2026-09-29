"""Join each research event and ledger row to the graph run that produced it

One inbound sensing message runs the agent graph once, and that run emits several research events
(detection, gate verdict, strategy, content, delivery) from several modules, plus one
`assistance_events` row when a card is sent. They could only be re-joined on
(session_id, cycle_number), which is ambiguous: both sensing channels share a cycle number, and the
browser restarts its counter on every lesson page while the session carries on.

`decision_id` is minted once per inbound message and stamped on everything that run writes, so
"which reading caused this card, and what did the learner do with it" is a single equality join.
Nullable: rows written before the migration, and events outside any run (a self-report, a page
visit), have none.

Revision ID: 031
Revises: 030
Create Date: 2026-09-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("research_events", sa.Column("decision_id", sa.String(36), nullable=True))
    op.create_index("ix_research_events_decision_id", "research_events", ["decision_id"])
    op.add_column("assistance_events", sa.Column("decision_id", sa.String(36), nullable=True))
    op.create_index("ix_assistance_events_decision_id", "assistance_events", ["decision_id"])


def downgrade() -> None:
    op.drop_index("ix_assistance_events_decision_id", table_name="assistance_events")
    op.drop_column("assistance_events", "decision_id")
    op.drop_index("ix_research_events_decision_id", table_name="research_events")
    op.drop_column("research_events", "decision_id")
