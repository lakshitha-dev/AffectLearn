"""Scope content-block ordering to the variant track

`content_blocks` has carried `variant_key` and `variant_group` since migration 005, and nothing
ever wrote anything but `"original"` into them — so the adaptation loop had no alternative content
to reach for and `show_alternative` / `increase_difficulty` fell through to generated text.

Authoring a variant means storing a sibling block in the SAME section, at the SAME position, that
stands in for the original when the loop selects it. `uq_content_blocks_section_sort` made that
impossible: two rows sharing (section_id, sort_order) violated it, so a variant would have had to
be parked at an arbitrary position past the end of the section, where its `sort_order` means
nothing and any future reordering could collide with it.

Adding `variant_key` to the constraint says what was always intended: a section may not have two
blocks in the same position *within one variant track*. The original track keeps exactly the
guarantee it had before this migration.

No data changes. Every existing row has `variant_key = 'original'`, so the new constraint is
satisfied by the same rows that satisfied the old one.

Revision ID: 028
Revises: 027
Create Date: 2026-09-06
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = "uq_content_blocks_section_sort"
_NEW = "uq_content_blocks_section_variant_sort"


def upgrade() -> None:
    # batch_alter_table so this also applies on SQLite, which cannot drop a constraint in place.
    with op.batch_alter_table("content_blocks") as batch:
        batch.drop_constraint(_OLD, type_="unique")
        batch.create_unique_constraint(_NEW, ["section_id", "variant_key", "sort_order"])


def downgrade() -> None:
    # Reverting narrows the constraint again. That fails if any authored variant shares a position
    # with its original — which is the normal state once variants exist — so a downgrade past this
    # point requires deleting non-original blocks first. Stated here rather than discovered.
    with op.batch_alter_table("content_blocks") as batch:
        batch.drop_constraint(_NEW, type_="unique")
        batch.create_unique_constraint(_OLD, ["section_id", "sort_order"])
