"""Content for the seeded demonstration courses (`app/db/seed_demo.py`).

These are NOT study content. The pilot courses in `app/db/course_content/` are system-owned,
affect-balanced and documented in the codebook; these are ordinary courses a designer might have
written, owned by the demo designer and flagged `is_demo` so no real participant is shown them.

They are built with the same helpers as the pilot content, so they render and adapt exactly like
real courses — including designer-authored variants, which the Content Adapter prefers over
generated text when it simplifies, re-explains or stretches a section.
"""

from __future__ import annotations

from app.models.course import BlockType, ContentBlock, Section


def with_variants(sec: Section, block_index: int, **variants: str) -> Section:
    """Attach authored variants (`simpler`, `harder`, `alternative`) to one text block.

    A variant stands in the same place as the block it replaces: same `sort_order`, same
    `variant_group`, a different `variant_key` (migration 028 scopes the ordering constraint to
    the variant track, which is what makes that legal).
    """
    original = sec.content_blocks[block_index]
    for key, body in variants.items():
        if key not in ("simpler", "harder", "alternative"):
            raise ValueError(f"unknown variant key {key!r}")
        sec.content_blocks.append(
            ContentBlock(
                block_type=BlockType.text,
                content={"text": body},
                sort_order=original.sort_order,
                variant_key=key,
                variant_group=original.variant_group,
            )
        )
    return sec
