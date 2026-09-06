"""Add courses.created_by — content ownership

Until now `require_role(course_designer, admin)` was the ONLY guard on every content mutation in
`courses.py`. Role is not ownership: any designer could edit, unpublish or DELETE any course,
including the seeded courses a pilot study depends on, and the API offered no way to tell whose
work was whose.

NULL means SYSTEM-OWNED. Courses created by `seed_courses.py` have no creating user, and every
course that predates this column is in the same position. Those become admin-only to edit, which
is the conservative reading and the one that protects seeded research content from a designer
with a delete button.

ON DELETE SET NULL, not CASCADE: removing a designer's account must not take their courses with
it. The content reverting to system-owned is the right outcome, and CASCADE here would make
deactivating a departing colleague destroy a live course.

Revision ID: 024
Revises: 023
Create Date: 2026-09-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_courses_created_by_users",
        "courses",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    # Indexed because "my courses" is the designer's default view and would otherwise scan the
    # whole catalogue on every load.
    op.create_index("ix_courses_created_by", "courses", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_courses_created_by", table_name="courses")
    op.drop_constraint("fk_courses_created_by_users", "courses", type_="foreignkey")
    op.drop_column("courses", "created_by")
