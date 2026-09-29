"""Record which consent text was agreed to, what it covered, and when it was withdrawn

`users.consent_given_at` recorded that a checkbox was ticked, not which text it sat under or which
kinds of capture it covered, and nothing on the server read it: the WebSocket processed facial and
behavioural data whether or not it was set.

This adds the consent text version, the optional scopes (behavioural capture, storage of raw
interaction events) and a withdrawal timestamp that stops all capture without deleting the account.
Webcam consent stays `webcam_enabled`. Existing rows get NULLs: a learner who consented before this
has no recorded version, and `services/consent.py` reads NULL scopes as the behaviour that was in
force when they consented (behavioural capture on, raw-event storage off).

Revision ID: 032
Revises: 031
Create Date: 2026-09-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("consent_version", sa.String(32), nullable=True))
    op.add_column("users", sa.Column("consent_scopes", sa.JSON, nullable=True))
    op.add_column(
        "users", sa.Column("consent_withdrawn_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "consent_withdrawn_at")
    op.drop_column("users", "consent_scopes")
    op.drop_column("users", "consent_version")
