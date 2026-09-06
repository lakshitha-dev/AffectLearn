"""Content versioning: what a measurement was taken on (migration 025).

Course content is mutated in place. Without a snapshot, "learners were confused in section X"
cannot be distinguished from "learners were confused in a section that has since been rewritten",
and nothing in the database says which it is. During a study that is worse than a missing number:
it is a number that looks current and is not.

Note what these tests deliberately do NOT assert: that learners are served the snapshot. They are
still served the live tree. Serving from a snapshot needs a draft/preview story and changes the
read path every learner depends on, and doing that as a side effect of an analytics fix would be
the wrong way round. What is delivered here is attribution.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_version import ContentVersion
from app.models.course import BlockType, ContentBlock, Course, Lesson, Module, Section
from app.models.section_progress import SectionProgress

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/courses"


@pytest_asyncio.fixture
async def authored_course(db: AsyncSession, test_designer):
    """A small course owned by the designer fixture, so publish is permitted."""
    course = Course(title="Versioned Course", is_published=False, created_by=test_designer.id)
    db.add(course)
    await db.flush()
    module = Module(title="Module One", sort_order=0, course_id=course.id)
    db.add(module)
    await db.flush()
    lesson = Lesson(title="Lesson One", sort_order=0, module_id=module.id)
    db.add(lesson)
    await db.flush()
    section = Section(title="Section One", sort_order=0, lesson_id=lesson.id)
    db.add(section)
    await db.flush()
    db.add(
        ContentBlock(
            section_id=section.id, block_type=BlockType.text, sort_order=0,
            variant_key="original", variant_group=uuid.uuid4(),
            content={"text": "The original wording."},
        )
    )
    await db.commit()
    # Plain ids, not ORM objects: `commit()` expires the instances, so touching an attribute
    # afterwards triggers a lazy refresh outside the async context and raises MissingGreenlet.
    return {
        "course_id": course.id,
        "module_id": module.id,
        "lesson_id": lesson.id,
        "section_id": section.id,
    }


async def _publish(client: AsyncClient, course_id, headers) -> None:
    resp = await client.put(
        f"{BASE}/{course_id}", json={"isPublished": True}, headers=headers
    )
    assert resp.status_code == 200


async def _published_version_id(db: AsyncSession, course_id):
    """Read the column fresh. The fixture hands out ids rather than ORM instances, so there is
    no attached `Course` to refresh."""
    return (
        await db.execute(select(Course.published_version_id).where(Course.id == course_id))
    ).scalars().first()


async def _versions(db: AsyncSession, course_id) -> list[ContentVersion]:
    return list(
        (
            await db.execute(
                select(ContentVersion)
                .where(ContentVersion.course_id == course_id)
                .order_by(ContentVersion.version_number)
            )
        ).scalars().all()
    )


class TestSnapshotOnPublish:

    async def test_publishing_creates_a_version(
        self, client: AsyncClient, authored_course, designer_headers, db: AsyncSession
    ):
        course_id = authored_course["course_id"]
        await _publish(client, course_id, designer_headers)

        versions = await _versions(db, course_id)
        assert len(versions) == 1
        assert versions[0].version_number == 1

    async def test_the_snapshot_captures_the_content_tree(
        self, client: AsyncClient, authored_course, designer_headers, db: AsyncSession
    ):
        course_id = authored_course["course_id"]
        await _publish(client, course_id, designer_headers)

        snapshot = (await _versions(db, course_id))[0].snapshot
        module = snapshot["modules"][0]
        block = module["lessons"][0]["sections"][0]["content_blocks"][0]

        assert module["title"] == "Module One"
        assert block["content"]["text"] == "The original wording."

    async def test_the_snapshot_keeps_ids(
        self, client: AsyncClient, authored_course, designer_headers, db: AsyncSession
    ):
        """Without ids a snapshot cannot be matched to the `section_id` a measurement carries,
        which is the whole reason for taking it."""
        course_id = authored_course["course_id"]
        section_id = authored_course["section_id"]
        await _publish(client, course_id, designer_headers)

        snapshot = (await _versions(db, course_id))[0].snapshot
        assert snapshot["modules"][0]["lessons"][0]["sections"][0]["id"] == str(section_id)

    async def test_the_course_points_at_its_latest_version(
        self, client: AsyncClient, authored_course, designer_headers, db: AsyncSession
    ):
        course_id = authored_course["course_id"]
        await _publish(client, course_id, designer_headers)

        published = await _published_version_id(db, course_id)
        versions = await _versions(db, course_id)
        assert published == versions[-1].id

    async def test_the_snapshot_records_who_published_it(
        self, client: AsyncClient, authored_course, designer_headers, test_designer,
        db: AsyncSession,
    ):
        course_id = authored_course["course_id"]
        await _publish(client, course_id, designer_headers)

        assert (await _versions(db, course_id))[0].published_by == test_designer.id

    async def test_republishing_adds_a_second_version(
        self, client: AsyncClient, authored_course, designer_headers, db: AsyncSession
    ):
        """Republishing an unchanged course still writes a version. Deduplicating would mean
        deciding what counts as a change, and getting that wrong in the quiet direction silently
        reattaches new measurements to old content."""
        course_id = authored_course["course_id"]
        await _publish(client, course_id, designer_headers)
        await client.put(f"{BASE}/{course_id}", json={"isPublished": False},
                         headers=designer_headers)
        await _publish(client, course_id, designer_headers)

        versions = await _versions(db, course_id)
        assert [v.version_number for v in versions] == [1, 2]

    async def test_an_edit_after_publishing_does_not_change_the_snapshot(
        self, client: AsyncClient, authored_course, designer_headers, db: AsyncSession
    ):
        """The point of the whole feature. The live tree moves on; the record of what was
        measured does not."""
        course_id = authored_course["course_id"]
        section_id = authored_course["section_id"]
        await _publish(client, course_id, designer_headers)

        await client.put(
            f"{BASE}/sections/{section_id}",
            json={"title": "Completely Rewritten"},
            headers=designer_headers,
        )

        snapshot = (await _versions(db, course_id))[0].snapshot
        assert snapshot["modules"][0]["lessons"][0]["sections"][0]["title"] == "Section One"

    async def test_a_non_publish_edit_creates_no_version(
        self, client: AsyncClient, authored_course, designer_headers, db: AsyncSession
    ):
        """Renaming a course is not a publish. Versioning every edit would produce hundreds of
        snapshots per paragraph, because the content editor autosaves as you type."""
        course_id = authored_course["course_id"]
        await client.put(
            f"{BASE}/{course_id}", json={"title": "Renamed"}, headers=designer_headers
        )

        assert await _versions(db, course_id) == []

    async def test_unpublishing_creates_no_version(
        self, client: AsyncClient, authored_course, designer_headers, db: AsyncSession
    ):
        course_id = authored_course["course_id"]
        await _publish(client, course_id, designer_headers)
        await client.put(
            f"{BASE}/{course_id}", json={"isPublished": False}, headers=designer_headers
        )

        assert len(await _versions(db, course_id)) == 1


class TestCompletionAttribution:

    async def test_a_completion_records_the_version_it_was_measured_on(
        self, client: AsyncClient, authored_course, designer_headers, auth_headers,
        test_user, db: AsyncSession,
    ):
        course_id = authored_course["course_id"]
        section_id = authored_course["section_id"]
        await _publish(client, course_id, designer_headers)

        await client.post("/api/v1/enrollments", json={"courseId": str(course_id)},
                          headers=auth_headers)
        await client.post(
            "/api/v1/section-progress",
            json={"sectionId": str(section_id), "timeSpentSeconds": 60},
            headers=auth_headers,
        )

        progress = (
            await db.execute(
                select(SectionProgress).where(SectionProgress.user_id == test_user.id)
            )
        ).scalar_one()
        assert progress.content_version_id == await _published_version_id(db, course_id)

    async def test_completions_on_a_course_published_before_versioning_have_none(
        self, client: AsyncClient, authored_course, auth_headers, test_user, db: AsyncSession
    ):
        """Migration 025 does not backfill: courses already published when it ran have no
        snapshot until someone republishes them. Their completions carry a null version, which
        is the honest answer — "there is no record of what this was measured on" — and not
        something to paper over with the current content.

        Published directly in the database rather than through the endpoint, because going
        through the endpoint is exactly what creates the version this case lacks.
        """
        course_id = authored_course["course_id"]
        section_id = authored_course["section_id"]
        course = await db.get(Course, course_id)
        course.is_published = True
        await db.commit()

        await client.post("/api/v1/enrollments", json={"courseId": str(course_id)},
                          headers=auth_headers)
        await client.post(
            "/api/v1/section-progress",
            json={"sectionId": str(section_id)},
            headers=auth_headers,
        )

        progress = (
            await db.execute(
                select(SectionProgress).where(SectionProgress.user_id == test_user.id)
            )
        ).scalar_one()
        assert progress.content_version_id is None

    async def test_completions_before_and_after_a_republish_are_distinguishable(
        self, client: AsyncClient, authored_course, designer_headers, auth_headers,
        db: AsyncSession,
    ):
        """The question the feature exists to answer: were these two learners looking at the
        same material?"""
        course_id = authored_course["course_id"]
        section_id = authored_course["section_id"]
        await _publish(client, course_id, designer_headers)
        first_version = await _published_version_id(db, course_id)

        await client.post("/api/v1/enrollments", json={"courseId": str(course_id)},
                          headers=auth_headers)
        await client.post(
            "/api/v1/section-progress", json={"sectionId": str(section_id)},
            headers=auth_headers,
        )

        # Rewrite and republish.
        await client.put(
            f"{BASE}/sections/{section_id}", json={"title": "Rewritten"},
            headers=designer_headers,
        )
        await client.put(f"{BASE}/{course_id}", json={"isPublished": False},
                         headers=designer_headers)
        await _publish(client, course_id, designer_headers)

        assert await _published_version_id(db, course_id) != first_version
        versions = await _versions(db, course_id)
        assert len(versions) == 2
        # And the two snapshots disagree, which is what makes the attribution meaningful.
        titles = [
            v.snapshot["modules"][0]["lessons"][0]["sections"][0]["title"] for v in versions
        ]
        assert titles == ["Section One", "Rewritten"]


class TestVersionCounting:

    async def test_version_numbers_are_per_course(
        self, client: AsyncClient, authored_course, designer_headers, db: AsyncSession
    ):
        course_id = authored_course["course_id"]
        await _publish(client, course_id, designer_headers)

        other = await client.post(BASE, json={"title": "Another"}, headers=designer_headers)
        other_id = uuid.UUID(other.json()["id"])
        await _publish(client, other_id, designer_headers)

        assert (await _versions(db, other_id))[0].version_number == 1

    async def test_deleting_a_course_removes_its_versions(
        self, client: AsyncClient, authored_course, designer_headers, db: AsyncSession
    ):
        """A snapshot of a course that no longer exists has nothing to describe — which is why
        this cascades where the research record deliberately does not."""
        course_id = authored_course["course_id"]
        await _publish(client, course_id, designer_headers)

        await client.delete(f"{BASE}/{course_id}", headers=designer_headers)

        remaining = (
            await db.execute(
                select(func.count(ContentVersion.id)).where(
                    ContentVersion.course_id == course_id
                )
            )
        ).scalar_one()
        assert remaining == 0


class TestVersionHistoryIsReadable:
    """`content_versions` was write-only.

    Snapshots have been captured on every publish since migration 025 and no endpoint returned
    one, so the table accumulated content trees nobody could look at. These cover the read that
    makes the feature usable, and the two properties that keep the list cheap and scoped.
    """

    async def test_lists_versions_newest_first_without_snapshots(
        self, client, designer_headers, db, test_designer
    ):
        from app.models.course import Course

        course = Course(title="Versioned", is_published=False, created_by=test_designer.id)
        db.add(course)
        await db.commit()
        await db.refresh(course)

        for _ in range(2):
            await client.put(
                f"/api/v1/courses/{course.id}",
                json={"isPublished": True},
                headers=designer_headers,
            )
            await client.put(
                f"/api/v1/courses/{course.id}",
                json={"isPublished": False},
                headers=designer_headers,
            )

        resp = await client.get(
            f"/api/v1/courses/{course.id}/versions", headers=designer_headers
        )
        assert resp.status_code == 200
        versions = resp.json()
        assert [v["versionNumber"] for v in versions] == sorted(
            [v["versionNumber"] for v in versions], reverse=True
        )
        # A snapshot is the whole content tree; a history table must not carry them.
        assert all("snapshot" not in v for v in versions)
        assert versions[0]["publishedByName"] is not None

    async def test_detail_returns_the_captured_tree(
        self, client, designer_headers, db, test_designer
    ):
        from app.models.course import Course

        course = Course(title="Snapshot Me", is_published=False, created_by=test_designer.id)
        db.add(course)
        await db.commit()
        await db.refresh(course)

        await client.put(
            f"/api/v1/courses/{course.id}",
            json={"isPublished": True},
            headers=designer_headers,
        )
        versions = (
            await client.get(f"/api/v1/courses/{course.id}/versions", headers=designer_headers)
        ).json()

        detail = await client.get(
            f"/api/v1/courses/versions/{versions[0]['id']}", headers=designer_headers
        )
        assert detail.status_code == 200
        assert isinstance(detail.json()["snapshot"], dict)

    async def test_another_designer_cannot_read_the_history(
        self, client, designer_headers, db, test_designer
    ):
        from app.core.security import create_access_token, hash_password
        from app.models.course import Course
        from app.models.user import Role, User

        course = Course(title="Private", is_published=True, created_by=test_designer.id)
        db.add(course)
        intruder = User(
            email_address="history-intruder@test.com",
            password_hash=hash_password("Password1!"),
            first_name="Not",
            last_name="Owner",
            role=Role.course_designer,
            email_verified=True,
        )
        db.add(intruder)
        await db.commit()
        await db.refresh(course)
        await db.refresh(intruder)

        resp = await client.get(
            f"/api/v1/courses/{course.id}/versions",
            headers={"Authorization": f"Bearer {create_access_token(str(intruder.id))}"},
        )
        assert resp.status_code == 403

    async def test_learner_cannot_read_the_history(self, client, auth_headers, test_course):
        resp = await client.get(
            f"/api/v1/courses/{test_course.id}/versions", headers=auth_headers
        )
        assert resp.status_code == 403
