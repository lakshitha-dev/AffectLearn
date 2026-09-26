"""Mark demonstration accounts and courses

A demo learner, a demo designer and a small background class are seeded so the platform can be
shown working with realistic data (`app/db/seed_demo.py`). They live in the same database as the
study's real participants, so they have to be identifiable: every research surface — the export,
the monitor CSV, the study audit, the educator review sample — excludes them by this flag, and
real learners are never shown a demo course in the catalogue.

A column rather than an email-domain convention because the rule has to hold for every query that
touches research data, and a string match on a naming habit is the kind of rule that silently
stops holding the first time someone registers with a similar address.

No data changes: every existing account and course is real, so the default is false.

Revision ID: 029
Revises: 028
Create Date: 2026-09-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Spelled out per table (not looped) so `test_migrations_cover_models` can see both columns.
    op.add_column(
        "users",
        sa.Column("is_demo", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_users_is_demo", "users", ["is_demo"])
    op.add_column(
        "courses",
        sa.Column("is_demo", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_courses_is_demo", "courses", ["is_demo"])


def downgrade() -> None:
    op.drop_index("ix_courses_is_demo", table_name="courses")
    op.drop_column("courses", "is_demo")
    op.drop_index("ix_users_is_demo", table_name="users")
    op.drop_column("users", "is_demo")
