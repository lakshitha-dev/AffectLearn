"""Tests for section progress tracking and lesson detail endpoints."""

import pytest
from httpx import AsyncClient


class TestMarkSectionComplete:
    async def test_happy_path_returns_201(self, client, enrolled_course, auth_headers):
        section = enrolled_course["sections"][0]
        resp = await client.post(
            "/api/v1/section-progress",
            json={"sectionId": str(section.id)},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["sectionId"] == str(section.id)

    async def test_idempotent_second_post_returns_200(self, client, enrolled_course, auth_headers):
        section = enrolled_course["sections"][0]
        payload = {"sectionId": str(section.id)}
        await client.post("/api/v1/section-progress", json=payload, headers=auth_headers)
        resp = await client.post("/api/v1/section-progress", json=payload, headers=auth_headers)
        assert resp.status_code == 200

    async def test_second_post_returns_same_record(self, client, enrolled_course, auth_headers):
        section = enrolled_course["sections"][0]
        payload = {"sectionId": str(section.id)}
        r1 = await client.post("/api/v1/section-progress", json=payload, headers=auth_headers)
        r2 = await client.post("/api/v1/section-progress", json=payload, headers=auth_headers)
        assert r1.json()["id"] == r2.json()["id"]

    async def test_not_enrolled_returns_403(self, client, test_course, db, auth_headers):
        from app.models.course import Lesson, Module, Section
        module = Module(title="M", sort_order=0, course_id=test_course.id)
        db.add(module)
        await db.flush()
        lesson = Lesson(title="L", sort_order=0, module_id=module.id)
        db.add(lesson)
        await db.flush()
        section = Section(title="S", sort_order=0, lesson_id=lesson.id)
        db.add(section)
        await db.commit()
        resp = await client.post("/api/v1/section-progress", json={"sectionId": str(section.id)}, headers=auth_headers)
        assert resp.status_code == 403

    async def test_nonexistent_section_returns_404(self, client, auth_headers):
        import uuid
        resp = await client.post("/api/v1/section-progress", json={"sectionId": str(uuid.uuid4())}, headers=auth_headers)
        assert resp.status_code == 404

    async def test_designer_cannot_mark_complete(self, client, enrolled_course, designer_headers):
        section = enrolled_course["sections"][0]
        resp = await client.post("/api/v1/section-progress", json={"sectionId": str(section.id)}, headers=designer_headers)
        assert resp.status_code == 403

    async def test_enrollment_progress_recomputed(self, client, enrolled_course, auth_headers, db):
        section = enrolled_course["sections"][0]
        await client.post("/api/v1/section-progress", json={"sectionId": str(section.id)}, headers=auth_headers)
        from sqlalchemy import select
        from app.models.enrollment import Enrollment
        enrollment = (await db.execute(select(Enrollment).where(Enrollment.course_id == enrolled_course["course"].id))).scalar_one()
        await db.refresh(enrollment)
        assert round(enrollment.progress_percentage, 1) == pytest.approx(8.3, abs=0.1)

    async def test_last_accessed_at_updated(self, client, enrolled_course, auth_headers, db):
        from sqlalchemy import select
        from app.models.enrollment import Enrollment
        section = enrolled_course["sections"][0]
        await client.post("/api/v1/section-progress", json={"sectionId": str(section.id)}, headers=auth_headers)
        enrollment = (await db.execute(select(Enrollment).where(Enrollment.course_id == enrolled_course["course"].id))).scalar_one()
        await db.refresh(enrollment)
        assert enrollment.last_accessed_at is not None

    async def test_admin_cannot_mark_complete(self, client, enrolled_course, admin_headers):
        section = enrolled_course["sections"][0]
        resp = await client.post(
            "/api/v1/section-progress",
            json={"sectionId": str(section.id)},
            headers=admin_headers,
        )
        assert resp.status_code == 403


class TestGetLessonProgress:
    async def test_returns_correct_totals(self, client, enrolled_course, auth_headers):
        section = enrolled_course["sections"][0]
        resp = await client.get(f"/api/v1/lessons/{section.lesson_id}/progress", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalSections"] == 3
        assert data["completedSectionIds"] == []

    async def test_returns_completed_ids(self, client, enrolled_course, auth_headers):
        section = enrolled_course["sections"][0]
        await client.post("/api/v1/section-progress", json={"sectionId": str(section.id)}, headers=auth_headers)
        resp = await client.get(f"/api/v1/lessons/{section.lesson_id}/progress", headers=auth_headers)
        data = resp.json()
        assert str(section.id) in data["completedSectionIds"]


class TestGetCourseProgress:
    async def test_returns_empty_initially(self, client, enrolled_course, auth_headers):
        course_id = enrolled_course["course"].id
        resp = await client.get(f"/api/v1/courses/{course_id}/progress", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["completedSectionIds"] == []

    async def test_returns_completed_ids(self, client, enrolled_course, auth_headers):
        section = enrolled_course["sections"][0]
        course_id = enrolled_course["course"].id
        await client.post("/api/v1/section-progress", json={"sectionId": str(section.id)}, headers=auth_headers)
        resp = await client.get(f"/api/v1/courses/{course_id}/progress", headers=auth_headers)
        assert str(section.id) in resp.json()["completedSectionIds"]


class TestGetLessonDetail:
    async def test_returns_lesson_with_sections_and_blocks(self, client, enrolled_course, auth_headers, db):
        from app.models.course import ContentBlock
        section = enrolled_course["sections"][0]
        block = ContentBlock(block_type="text", content={"text": "Hello"}, sort_order=0, section_id=section.id)
        db.add(block)
        await db.commit()
        resp = await client.get(f"/api/v1/courses/lessons/{section.lesson_id}/detail", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(section.lesson_id)
        assert any(s["id"] == str(section.id) for s in data["sections"])

    async def test_nonexistent_lesson_returns_404(self, client, auth_headers):
        import uuid
        resp = await client.get(f"/api/v1/courses/lessons/{uuid.uuid4()}/detail", headers=auth_headers)
        assert resp.status_code == 404

    async def test_designer_can_access(self, client, enrolled_course, designer_headers):
        section = enrolled_course["sections"][0]
        resp = await client.get(f"/api/v1/courses/lessons/{section.lesson_id}/detail", headers=designer_headers)
        assert resp.status_code == 200

    async def test_admin_can_access(self, client, enrolled_course, admin_headers):
        section = enrolled_course["sections"][0]
        resp = await client.get(f"/api/v1/courses/lessons/{section.lesson_id}/detail", headers=admin_headers)
        assert resp.status_code == 200
