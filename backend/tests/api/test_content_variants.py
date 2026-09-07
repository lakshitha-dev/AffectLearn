"""Tests for content-block variants (FR19 / FR21).

`content_blocks` has carried `variant_key` and `variant_group` since migration 005 and nothing
ever wrote anything but `"original"`, so the adaptation loop had no authored alternative to reach
for: `show_alternative` and `increase_difficulty` fell through to generated text and `skip_ahead`
degraded to "the next section".

Two properties matter most here and are covered first:

* a variant must NOT reach learners as ordinary content — otherwise authoring one turns a section
  into the same idea explained twice in a row;
* saving the same key twice must edit rather than fork, because the loop selects BY key and two
  blocks answering to one key makes which a learner sees arbitrary.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/courses"


async def _build_section(client: AsyncClient, headers: dict) -> tuple[str, str]:
    """A published course with one section holding one text block. Returns (sectionId, blockId)."""
    course = (
        await client.post(
            BASE,
            json={"title": "Variants Course", "description": "d", "isPublished": True},
            headers=headers,
        )
    ).json()
    module = (
        await client.post(
            f"{BASE}/{course['id']}/modules",
            json={"title": "M", "description": "d", "sortOrder": 0},
            headers=headers,
        )
    ).json()
    lesson = (
        await client.post(
            f"{BASE}/modules/{module['id']}/lessons",
            json={"title": "L", "description": "d", "sortOrder": 0},
            headers=headers,
        )
    ).json()
    section = (
        await client.post(
            f"{BASE}/lessons/{lesson['id']}/sections",
            json={"title": "S", "sortOrder": 0, "estimatedDurationMinutes": 5},
            headers=headers,
        )
    ).json()
    block = (
        await client.post(
            f"{BASE}/sections/{section['id']}/content-blocks",
            json={"blockType": "text", "content": {"text": "The original"}, "sortOrder": 0},
            headers=headers,
        )
    ).json()
    return section["id"], block["id"], lesson["id"]


class TestAuthoringVariants:
    async def test_creates_a_variant_sharing_the_group(
        self, client: AsyncClient, designer_headers
    ):
        section_id, block_id, _ = await _build_section(client, designer_headers)

        resp = await client.post(
            f"{BASE}/content-blocks/{block_id}/variants",
            json={"variantKey": "simpler", "content": {"text": "Put more simply"}},
            headers=designer_headers,
        )
        assert resp.status_code == 201
        variant = resp.json()
        assert variant["variantKey"] == "simpler"
        assert variant["id"] != block_id

        original = (
            await client.get(
                f"{BASE}/content-blocks/{block_id}/variants", headers=designer_headers
            )
        ).json()
        assert {v["variantKey"] for v in original} == {"original", "simpler"}
        # One family: the group is what ties a variant to the block it stands in for.
        assert len({v["variantGroup"] for v in original}) == 1

    async def test_variant_shares_the_originals_position(
        self, client: AsyncClient, designer_headers
    ):
        """The unique constraint had to be widened for this to be possible at all.

        A variant substitutes for its original in place, so it carries the same `sortOrder`.
        Under the old (section_id, sort_order) constraint this insert failed.
        """
        _, block_id, _ = await _build_section(client, designer_headers)

        resp = await client.post(
            f"{BASE}/content-blocks/{block_id}/variants",
            json={"variantKey": "harder", "content": {"text": "Now try this"}},
            headers=designer_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["sortOrder"] == 0

    async def test_saving_the_same_key_twice_edits_rather_than_forks(
        self, client: AsyncClient, designer_headers
    ):
        _, block_id, _ = await _build_section(client, designer_headers)

        first = await client.post(
            f"{BASE}/content-blocks/{block_id}/variants",
            json={"variantKey": "simpler", "content": {"text": "v1"}},
            headers=designer_headers,
        )
        second = await client.post(
            f"{BASE}/content-blocks/{block_id}/variants",
            json={"variantKey": "simpler", "content": {"text": "v2"}},
            headers=designer_headers,
        )

        assert first.json()["id"] == second.json()["id"]
        assert second.json()["content"] == {"text": "v2"}

        variants = (
            await client.get(
                f"{BASE}/content-blocks/{block_id}/variants", headers=designer_headers
            )
        ).json()
        assert len(variants) == 2  # original + one simpler, not two simplers

    async def test_rejects_a_key_the_loop_cannot_select(
        self, client: AsyncClient, designer_headers
    ):
        """A free-text key would let a designer author content nothing ever reaches."""
        _, block_id, _ = await _build_section(client, designer_headers)

        resp = await client.post(
            f"{BASE}/content-blocks/{block_id}/variants",
            json={"variantKey": "spicier", "content": {"text": "?"}},
            headers=designer_headers,
        )
        assert resp.status_code == 422


class TestVariantsDoNotLeakIntoTheLesson:
    """The property that makes authoring a variant safe."""

    async def test_learner_lesson_detail_shows_only_the_original(
        self, client: AsyncClient, designer_headers, auth_headers
    ):
        section_id, block_id, lesson_id = await _build_section(client, designer_headers)
        await client.post(
            f"{BASE}/content-blocks/{block_id}/variants",
            json={"variantKey": "simpler", "content": {"text": "Put more simply"}},
            headers=designer_headers,
        )

        detail = (
            await client.get(f"{BASE}/lessons/{lesson_id}/detail", headers=auth_headers)
        ).json()
        blocks = detail["sections"][0]["contentBlocks"]

        assert [b["content"]["text"] for b in blocks] == ["The original"]

    async def test_learner_block_list_shows_only_the_original(
        self, client: AsyncClient, designer_headers, auth_headers
    ):
        section_id, block_id, _ = await _build_section(client, designer_headers)
        await client.post(
            f"{BASE}/content-blocks/{block_id}/variants",
            json={"variantKey": "harder", "content": {"text": "Now try this"}},
            headers=designer_headers,
        )

        blocks = (
            await client.get(
                f"{BASE}/sections/{section_id}/content-blocks", headers=auth_headers
            )
        ).json()
        assert [b["variantKey"] for b in blocks] == ["original"]

    async def test_designer_still_sees_every_variant(
        self, client: AsyncClient, designer_headers
    ):
        """Designers author the alternatives, so they must be able to see that they exist."""
        section_id, block_id, _ = await _build_section(client, designer_headers)
        await client.post(
            f"{BASE}/content-blocks/{block_id}/variants",
            json={"variantKey": "simpler", "content": {"text": "Put more simply"}},
            headers=designer_headers,
        )

        blocks = (
            await client.get(
                f"{BASE}/sections/{section_id}/content-blocks", headers=designer_headers
            )
        ).json()
        assert {b["variantKey"] for b in blocks} == {"original", "simpler"}


class TestVariantAuthoringIsScoped:
    async def test_learner_cannot_author_a_variant(
        self, client: AsyncClient, designer_headers, auth_headers
    ):
        _, block_id, _ = await _build_section(client, designer_headers)

        resp = await client.post(
            f"{BASE}/content-blocks/{block_id}/variants",
            json={"variantKey": "simpler", "content": {"text": "nope"}},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    async def test_another_designer_cannot_author_a_variant(
        self, client: AsyncClient, db, designer_headers
    ):
        from app.core.security import create_access_token, hash_password
        from app.models.user import Role, User

        _, block_id, _ = await _build_section(client, designer_headers)

        intruder = User(
            email_address="variant-intruder@test.com",
            password_hash=hash_password("Password1!"),
            first_name="Not",
            last_name="Owner",
            role=Role.course_designer,
            email_verified=True,
        )
        db.add(intruder)
        await db.commit()
        await db.refresh(intruder)

        resp = await client.post(
            f"{BASE}/content-blocks/{block_id}/variants",
            json={"variantKey": "simpler", "content": {"text": "nope"}},
            headers={"Authorization": f"Bearer {create_access_token(str(intruder.id))}"},
        )
        assert resp.status_code == 403
