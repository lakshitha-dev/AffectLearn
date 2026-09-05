"""Add content coordinates (course_id, section_id, block_id) to research_events

Migration 016 promoted `phase` and `group` out of the JSON payload into indexed columns because
they are join keys, not attributes. This does the same for the three coordinates that say WHERE IN
THE COURSE an event happened.

Until now the affect and adaptation events carried `learner_id`, `session_id` and `cycle_number`
and nothing else locating them. `analytics_service` records the consequence in its own header:
`research_events` rows are "keyed by `session_id` + `cycle_number`, NOT by `section_id`", so its
per-section aggregations are best-effort and the affect heatmap is built instead from
`section_progress.affect_states` -- a list the CLIENT posts on completion, not the model's own
output. Anything that wants to ask "which section produces confusion", "where is help requested
most" or "did this hint help on this question" needs the join key to exist first.

The section id was already available at every emit site (the browser sends it on `facial_features`
and `behavioral_window`, and `content_context_service` resolves it); it simply was never written
down. This migration adds the columns; the emit sites populate them.

All three are NULLABLE. Connection-level events (`ws_connected`, `ws_disconnected`) and
account-level ones (`questionnaire_submitted`, `survey_completed`) have no content coordinate, and
every row written before this migration predates the column. Aggregations therefore filter on
`IS NOT NULL` rather than assuming presence.

All three are String(64), not UUID foreign keys, matching `learner_id` / `session_id` above them.
`research_events` is an append-only research record and must survive the deletion of the content it
refers to: a designer removing a section must not cascade away the evidence of what learners did
inside it.

Revision ID: 021
Revises: 020
Create Date: 2026-09-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("course_id", "section_id", "block_id")


def upgrade() -> None:
    for column in _COLUMNS:
        op.add_column(
            "research_events", sa.Column(column, sa.String(length=64), nullable=True)
        )
        # Indexed because every per-section aggregate filters on these, and the table grows by
        # one row per modality per 30s cycle per learner -- a sequential scan here is the whole
        # dataset.
        op.create_index(
            f"ix_research_events_{column}", "research_events", [column]
        )


def downgrade() -> None:
    for column in reversed(_COLUMNS):
        op.drop_index(f"ix_research_events_{column}", table_name="research_events")
        op.drop_column("research_events", column)
