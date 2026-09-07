"""Tests for the designer course roster.

A designer had no way to see who was enrolled on their own course. The one learner aggregate that
existed spans EVERY course a learner is enrolled in, so widening it would have handed one designer
another designer's learner data; this is course-scoped by construction instead.
"""

import uuid

import pytest

pytestmark = pytest.mark.asyncio


def _url(course_id):
    return f"/api/v1/learners/courses/{course_id}/roster"


async def test_lists_enrolled_learners_with_progress(
    client, designer_headers, auth_headers, enrolled_course, test_user
):
    course = enrolled_course["course"]
    section = enrolled_course["sections"][0]
    await client.post(
        "/api/v1/section-progress",
        headers=auth_headers,
        json={"sectionId": str(section.id), "timeSpentSeconds": 30},
    )

    resp = await client.get(_url(course.id), headers=designer_headers)

    assert resp.status_code == 200
    roster = resp.json()
    assert len(roster) == 1
    entry = roster[0]
    assert entry["userId"] == str(test_user.id)
    assert entry["emailAddress"] == "learner@test.com"
    assert entry["completedSections"] == 1
    assert entry["totalSections"] == 12


async def test_counts_only_this_courses_sections(
    client, designer_headers, auth_headers, enrolled_course, db, test_user, test_designer
):
    """A learner on several courses must not have the others counted into this figure."""
    from app.models.course import Course, Lesson, Module, Section
    from app.models.enrollment import Enrollment

    other = Course(title="Other", is_published=True, created_by=test_designer.id)
    db.add(other)
    await db.flush()
    module = Module(title="M", sort_order=0, course_id=other.id)
    db.add(module)
    await db.flush()
    lesson = Lesson(title="L", sort_order=0, module_id=module.id)
    db.add(lesson)
    await db.flush()
    other_section = Section(title="S", sort_order=0, lesson_id=lesson.id)
    db.add(other_section)
    db.add(Enrollment(user_id=test_user.id, course_id=other.id))
    await db.commit()
    await db.refresh(other_section)

    # Complete a section in the OTHER course only.
    await client.post(
        "/api/v1/section-progress",
        headers=auth_headers,
        json={"sectionId": str(other_section.id)},
    )

    roster = (
        await client.get(_url(enrolled_course["course"].id), headers=designer_headers)
    ).json()
    assert roster[0]["completedSections"] == 0


async def test_learner_with_no_progress_reports_zero_not_missing(
    client, designer_headers, enrolled_course
):
    roster = (
        await client.get(_url(enrolled_course["course"].id), headers=designer_headers)
    ).json()
    assert roster[0]["completedSections"] == 0


async def test_shows_learners_who_have_left(
    client, designer_headers, auth_headers, enrolled_course
):
    """Leaving is a status change, so a dropped learner stays visible — with their status."""
    course_id = enrolled_course["course"].id
    await client.post(f"/api/v1/enrollments/{course_id}/drop", headers=auth_headers)

    roster = (await client.get(_url(course_id), headers=designer_headers)).json()
    assert roster[0]["status"] == "dropped"


async def test_learners_cannot_read_a_roster(client, auth_headers, enrolled_course):
    resp = await client.get(_url(enrolled_course["course"].id), headers=auth_headers)
    assert resp.status_code == 403


async def test_another_designer_cannot_read_the_roster(
    client, db, enrolled_course, test_designer
):
    from app.core.security import create_access_token, hash_password
    from app.models.user import Role, User

    intruder = User(
        email_address="roster-intruder@test.com",
        password_hash=hash_password("Password1!"),
        first_name="Not",
        last_name="Owner",
        role=Role.course_designer,
        email_verified=True,
    )
    db.add(intruder)
    await db.commit()
    await db.refresh(intruder)

    resp = await client.get(
        _url(enrolled_course["course"].id),
        headers={"Authorization": f"Bearer {create_access_token(str(intruder.id))}"},
    )
    assert resp.status_code == 403


async def test_unknown_course_is_404(client, designer_headers):
    resp = await client.get(_url(uuid.uuid4()), headers=designer_headers)
    assert resp.status_code == 404
