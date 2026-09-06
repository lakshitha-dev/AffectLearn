"""Create system_config, and stamp config_version onto research events

Every knob governing the study was an environment variable: changing one meant editing Azure app
settings and restarting, which is invisible to the research record and unsafe once collection has
begun. This table makes them runtime-editable, and adds the two things that make that safe.

`research_events.config_version` is the more important half. If a confidence floor or the trial
withhold rate changes halfway through collection, the cycles before and after are no longer
comparable — and without this column nothing in the dataset would show that it happened. An
analysis would silently pool incomparable observations. Indexed, because splitting an analysis on
it is the entire reason it exists.

Existing rows get version 1 rather than NULL: they were produced under one configuration (the
deployed environment) and belong together, so a null would misrepresent them as unknown.

Revision ID: 027
Revises: 026
Create Date: 2026-09-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        # Bumped on EVERY mutation, including a lock or a key rotation.
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        # Only the keys an admin has explicitly overridden; absent -> env/code default. This is
        # what lets a fresh deploy against an empty row behave exactly as the deployment did
        # before the table existed.
        sa.Column("values", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        # Fernet ciphertext. No code path decrypts this for display.
        sa.Column("llm_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("llm_api_key_hint", sa.String(length=8), nullable=True),
        sa.Column("llm_api_key_updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Nullable first so the backfill does not need a table rewrite with a lock held.
    op.add_column("research_events", sa.Column("config_version", sa.Integer(), nullable=True))
    op.execute("UPDATE research_events SET config_version = 1 WHERE config_version IS NULL")
    op.create_index(
        "ix_research_events_config_version", "research_events", ["config_version"]
    )


def downgrade() -> None:
    op.drop_index("ix_research_events_config_version", table_name="research_events")
    op.drop_column("research_events", "config_version")
    op.drop_table("system_config")
