"""Course ownership: role is not authorisation (migration 024).

Until `courses.created_by` existed, `require_role(course_designer, admin)` was the ONLY guard on
every content mutation. Any designer could edit, unpublish or DELETE any course, including the
seeded courses a pilot study depends on.

The guard has to hold at every level of the content tree, not only on the course itself: a
designer edits a CONTENT BLOCK, and guarding `PUT /courses/{id}` while leaving
`PUT /content-blocks/{id}` open would be a guard in name only. Each test below therefore reaches
for a different level.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.course import BlockType, ContentBlock, Course, Lesson, Module, Section
from app.models.user import Role, User

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/courses"


@pytest_asyncio.fixture
async def other_designer(db: AsyncSession) -> User:
    user = User(
        email_address="other-designer@test.com",
        password_hash=hash_password("Password1!"),
        first_name="Other",
        last_name="Designer",
        role=Role.course_designer,
        email_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
def other_designer_headers(other_designer: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(other_designer.id))}"}


async def _tree(db: AsyncSession, *, created_by):
    """A full course tree owned by `created_by` (None means seeded system content)."""
    course = Course(title="Owned Course", is_published=False, created_by=created_by)
    db.add(course)
    await db.flush()
    module = Module(title="M", sort_order=0, course_id=course.id)
    db.add(module)
    await db.flush()
    lesson = Lesson(title="L", sort_order=0, module_id=module.id)
    db.add(lesson)
    await db.flush()
    section = Section(title="S", sort_order=0, lesson_id=lesson.id)
    db.add(section)
    await db.flush()
    block = ContentBlock(
        section_id=section.id, block_type=BlockType.text, sort_order=0,
        variant_key="original", variant_group=uuid.uuid4(), content={"text": "hi"},
    )
    db.add(block)
    await db.commit()
    return course, module, lesson, section, block


class TestOwnershipIsStamped:

    async def test_creating_a_course_records_its_author(
        self, client: AsyncClient, designer_headers, test_designer, db: AsyncSession
    ):
        resp = await client.post(
            BASE, json={"title": "Mine"}, headers=designer_headers
        )
        assert resp.status_code == 201

        course = await db.get(Course, uuid.UUID(resp.json()["id"]))
        assert course.created_by == test_designer.id

    async def test_an_admin_created_course_is_owned_not_system(
        self, client: AsyncClient, admin_headers, test_admin, db: AsyncSession
    ):
        """Leaving it NULL would make it system content its own author could not edit as a
        designer later."""
        resp = await client.post(BASE, json={"title": "Admins"}, headers=admin_headers)

        course = await db.get(Course, uuid.UUID(resp.json()["id"]))
        assert course.created_by == test_admin.id


class TestADesignerCannotTouchAnotherDesignersCourse:

    async def test_cannot_update_the_course(
        self, client: AsyncClient, other_designer_headers, test_designer, db: AsyncSession
    ):
        course, *_ = await _tree(db, created_by=test_designer.id)

        resp = await client.put(
            f"{BASE}/{course.id}", json={"title": "Hijacked"},
            headers=other_designer_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"]["code"] == "NOT_COURSE_OWNER"

    async def test_cannot_delete_the_course(
        self, client: AsyncClient, other_designer_headers, test_designer, db: AsyncSession
    ):
        course, *_ = await _tree(db, created_by=test_designer.id)

        resp = await client.delete(f"{BASE}/{course.id}", headers=other_designer_headers)
        assert resp.status_code == 403

    async def test_cannot_publish_the_course(
        self, client: AsyncClient, other_designer_headers, test_designer, db: AsyncSession
    ):
        """Publishing is a mutation like any other, and an unpublish is a denial of service on
        someone else's live course."""
        course, *_ = await _tree(db, created_by=test_designer.id)

        resp = await client.put(
            f"{BASE}/{course.id}", json={"isPublished": True},
            headers=other_designer_headers,
        )
        assert resp.status_code == 403

    async def test_cannot_delete_a_module_inside_it(
        self, client: AsyncClient, other_designer_headers, test_designer, db: AsyncSession
    ):
        _, module, *_ = await _tree(db, created_by=test_designer.id)

        resp = await client.delete(
            f"{BASE}/modules/{module.id}", headers=other_designer_headers
        )
        assert resp.status_code == 403

    async def test_cannot_delete_a_lesson_inside_it(
        self, client: AsyncClient, other_designer_headers, test_designer, db: AsyncSession
    ):
        _, _, lesson, _, _ = await _tree(db, created_by=test_designer.id)

        resp = await client.delete(
            f"{BASE}/lessons/{lesson.id}", headers=other_designer_headers
        )
        assert resp.status_code == 403

    async def test_cannot_edit_a_section_inside_it(
        self, client: AsyncClient, other_designer_headers, test_designer, db: AsyncSession
    ):
        _, _, _, section, _ = await _tree(db, created_by=test_designer.id)

        resp = await client.put(
            f"{BASE}/sections/{section.id}", json={"title": "Rewritten"},
            headers=other_designer_headers,
        )
        assert resp.status_code == 403

    async def test_cannot_edit_a_content_block_inside_it(
        self, client: AsyncClient, other_designer_headers, test_designer, db: AsyncSession
    ):
        """The deepest level, and the one a guard on `/courses/{id}` alone would miss entirely."""
        _, _, _, _, block = await _tree(db, created_by=test_designer.id)

        resp = await client.put(
            f"{BASE}/content-blocks/{block.id}", json={"content": {"text": "changed"}},
            headers=other_designer_headers,
        )
        assert resp.status_code == 403

    async def test_cannot_add_a_module_to_it(
        self, client: AsyncClient, other_designer_headers, test_designer, db: AsyncSession
    ):
        course, *_ = await _tree(db, created_by=test_designer.id)

        resp = await client.post(
            f"{BASE}/{course.id}/modules", json={"title": "Injected", "sortOrder": 9},
            headers=other_designer_headers,
        )
        assert resp.status_code == 403


class TestSeededContentIsAdminOnly:
    """`created_by IS NULL` means system content. Treating unowned as "anyone may edit" would
    leave the pilot courses exactly as exposed as they were before."""

    async def test_a_designer_cannot_edit_seeded_content(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        course, *_ = await _tree(db, created_by=None)

        resp = await client.put(
            f"{BASE}/{course.id}", json={"title": "Edited"}, headers=designer_headers
        )
        assert resp.status_code == 403
        assert "administrator" in resp.json()["detail"]["error"]["message"]

    async def test_a_designer_cannot_delete_seeded_content(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        """The exact risk: a designer with a delete button and a live pilot course."""
        course, *_ = await _tree(db, created_by=None)

        resp = await client.delete(f"{BASE}/{course.id}", headers=designer_headers)
        assert resp.status_code == 403

    async def test_an_admin_can_edit_seeded_content(
        self, client: AsyncClient, admin_headers, db: AsyncSession
    ):
        course, *_ = await _tree(db, created_by=None)

        resp = await client.put(
            f"{BASE}/{course.id}", json={"title": "Corrected"}, headers=admin_headers
        )
        assert resp.status_code == 200


class TestOwnersAndAdminsRetainAccess:

    async def test_the_owner_can_still_edit_their_own_course(
        self, client: AsyncClient, designer_headers, test_designer, db: AsyncSession
    ):
        course, *_ = await _tree(db, created_by=test_designer.id)

        resp = await client.put(
            f"{BASE}/{course.id}", json={"title": "Revised"}, headers=designer_headers
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Revised"

    async def test_the_owner_can_still_edit_a_block_inside_it(
        self, client: AsyncClient, designer_headers, test_designer, db: AsyncSession
    ):
        _, _, _, _, block = await _tree(db, created_by=test_designer.id)

        resp = await client.put(
            f"{BASE}/content-blocks/{block.id}", json={"content": {"text": "revised"}},
            headers=designer_headers,
        )
        assert resp.status_code == 200

    async def test_an_admin_can_edit_anyone_elses_course(
        self, client: AsyncClient, admin_headers, test_designer, db: AsyncSession
    ):
        course, *_ = await _tree(db, created_by=test_designer.id)

        resp = await client.put(
            f"{BASE}/{course.id}", json={"title": "Moderated"}, headers=admin_headers
        )
        assert resp.status_code == 200

    async def test_learners_are_still_refused_by_role_before_ownership(
        self, client: AsyncClient, auth_headers, test_designer, db: AsyncSession
    ):
        """Ownership is layered ON TOP of the role guard, not instead of it."""
        course, *_ = await _tree(db, created_by=test_designer.id)

        resp = await client.put(
            f"{BASE}/{course.id}", json={"title": "Nope"}, headers=auth_headers
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"]["code"] == "FORBIDDEN"


class TestReadingIsUnaffected:

    async def test_a_designer_can_still_read_another_designers_course(
        self, client: AsyncClient, other_designer_headers, test_designer, db: AsyncSession
    ):
        """Ownership restricts WRITES. Reading the catalogue is how a designer finds the course
        they need an admin to hand over."""
        course, *_ = await _tree(db, created_by=test_designer.id)

        resp = await client.get(f"{BASE}/{course.id}", headers=other_designer_headers)
        assert resp.status_code == 200


class TestUnknownContent:

    async def test_editing_a_missing_course_is_404_not_403(
        self, client: AsyncClient, designer_headers
    ):
        """A 403 here would tell a caller that a course id exists when it does not."""
        resp = await client.put(
            f"{BASE}/{uuid.uuid4()}", json={"title": "Ghost"}, headers=designer_headers
        )
        assert resp.status_code == 404


class TestOwnershipIsVisibleToTheUi:
    """The authoring UI decides whether to render Edit and Delete from `canEdit`. A list that
    offers actions the API will refuse teaches people to distrust its buttons, and re-deriving
    the rule in TypeScript would be the same authorisation written twice, in two languages."""

    async def test_a_designer_sees_can_edit_true_for_their_own_course(
        self, client: AsyncClient, designer_headers, test_designer, db: AsyncSession
    ):
        course, *_ = await _tree(db, created_by=test_designer.id)

        resp = await client.get(f"{BASE}/{course.id}", headers=designer_headers)
        assert resp.json()["canEdit"] is True

    async def test_a_designer_sees_can_edit_false_for_someone_elses(
        self, client: AsyncClient, other_designer_headers, test_designer, db: AsyncSession
    ):
        course, *_ = await _tree(db, created_by=test_designer.id)

        resp = await client.get(f"{BASE}/{course.id}", headers=other_designer_headers)
        assert resp.json()["canEdit"] is False

    async def test_a_designer_sees_can_edit_false_for_seeded_content(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        course, *_ = await _tree(db, created_by=None)

        resp = await client.get(f"{BASE}/{course.id}", headers=designer_headers)
        assert resp.json()["canEdit"] is False
        assert resp.json()["createdBy"] is None

    async def test_an_admin_sees_can_edit_true_for_everything(
        self, client: AsyncClient, admin_headers, test_designer, db: AsyncSession
    ):
        owned, *_ = await _tree(db, created_by=test_designer.id)
        seeded, *_ = await _tree(db, created_by=None)

        for course in (owned, seeded):
            resp = await client.get(f"{BASE}/{course.id}", headers=admin_headers)
            assert resp.json()["canEdit"] is True

    async def test_the_list_view_carries_it_too(
        self, client: AsyncClient, designer_headers, test_designer, db: AsyncSession
    ):
        await _tree(db, created_by=test_designer.id)
        await _tree(db, created_by=None)

        items = (await client.get(BASE, headers=designer_headers)).json()["items"]
        assert {item["canEdit"] for item in items} == {True, False}

    async def test_learners_are_told_nothing_about_authorship(
        self, client: AsyncClient, auth_headers, test_designer, db: AsyncSession
    ):
        """A learner has no use for it, and who wrote a course is not theirs to know."""
        course, *_ = await _tree(db, created_by=test_designer.id)
        course.is_published = True
        await db.commit()

        resp = await client.get(f"{BASE}/{course.id}", headers=auth_headers)
        assert resp.json()["canEdit"] is None
        assert resp.json()["createdBy"] is None
