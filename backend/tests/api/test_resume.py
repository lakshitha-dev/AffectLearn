"""Tests for the resume target endpoint."""

import pytest
from httpx import AsyncClient


class TestGetResumeTarget:
    """GET /api/v1/enrollments/{course_id}/resume"""

    async def test_happy_path_returns_first_incomplete(
        self, client: AsyncClient, enrolled_course, auth_headers
    ):
        """Zero completions -> first section is the resume target."""
        course_id = enrolled_course["course"].id
        resp = await client.get(
            f"/api/v1/enrollments/{course_id}/resume",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # First section in sort_order order
        first_section = enrolled_course["sections"][0]
        assert data["sectionId"] == str(first_section.id)
        assert data["isCourseComplete"] is False

    async def test_partial_completion_returns_next_incomplete(
        self, client: AsyncClient, enrolled_course, auth_headers
    ):
        """With 4 sections complete, resume target is the 5th."""
        sections = enrolled_course["sections"]
        course_id = enrolled_course["course"].id

        # Complete the first 4 sections
        for s in sections[:4]:
            await client.post(
                "/api/v1/section-progress",
                json={"sectionId": str(s.id)},
                headers=auth_headers,
            )

        resp = await client.get(
            f"/api/v1/enrollments/{course_id}/resume",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sectionId"] == str(sections[4].id)
        assert data["isCourseComplete"] is False

    async def test_all_complete_returns_last_section(
        self, client: AsyncClient, enrolled_course, auth_headers
    ):
        """All sections complete -> isCourseComplete=True, target is last section."""
        sections = enrolled_course["sections"]
        course_id = enrolled_course["course"].id

        for s in sections:
            await client.post(
                "/api/v1/section-progress",
                json={"sectionId": str(s.id)},
                headers=auth_headers,
            )

        resp = await client.get(
            f"/api/v1/enrollments/{course_id}/resume",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["isCourseComplete"] is True
        assert data["sectionId"] == str(sections[-1].id)

    async def test_not_enrolled_returns_404(
        self, client: AsyncClient, test_course, auth_headers
    ):
        """User not enrolled -> 404 NOT_ENROLLED."""
        resp = await client.get(
            f"/api/v1/enrollments/{test_course.id}/resume",
            headers=auth_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["error"]["code"] == "NOT_ENROLLED"

    async def test_course_empty_returns_404(
        self, client: AsyncClient, db, auth_headers, test_user
    ):
        """Course with no sections -> 404 COURSE_EMPTY."""
        from app.models.course import Course
        from app.models.enrollment import Enrollment
        empty_course = Course(title="Empty", is_published=True)
        db.add(empty_course)
        await db.flush()
        enrollment = Enrollment(user_id=test_user.id, course_id=empty_course.id)
        db.add(enrollment)
        await db.commit()

        resp = await client.get(
            f"/api/v1/enrollments/{empty_course.id}/resume",
            headers=auth_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["error"]["code"] == "COURSE_EMPTY"

    async def test_designer_gets_403(
        self, client: AsyncClient, enrolled_course, designer_headers
    ):
        course_id = enrolled_course["course"].id
        resp = await client.get(
            f"/api/v1/enrollments/{course_id}/resume",
            headers=designer_headers,
        )
        assert resp.status_code == 403

    async def test_admin_gets_403(
        self, client: AsyncClient, enrolled_course, admin_headers
    ):
        course_id = enrolled_course["course"].id
        resp = await client.get(
            f"/api/v1/enrollments/{course_id}/resume",
            headers=admin_headers,
        )
        assert resp.status_code == 403

    async def test_unauthenticated_gets_401_or_403(
        self, client: AsyncClient, enrolled_course
    ):
        """No auth header -> HTTPBearer raises 403 (or 401 depending on FastAPI version)."""
        course_id = enrolled_course["course"].id
        resp = await client.get(f"/api/v1/enrollments/{course_id}/resume")
        assert resp.status_code in (401, 403)
