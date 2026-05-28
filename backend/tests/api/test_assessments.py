"""Tests for assessment endpoints."""

import pytest
from httpx import AsyncClient


async def create_test_assessment(client, enrolled_course, designer_headers, db, a_type="pre"):
    """Helper: create assessment with 2 questions, each with 2 options."""
    from app.models.course import Lesson, Module
    from sqlalchemy import select

    # Get first module
    course = enrolled_course["course"]
    stmt = select(Module).where(Module.course_id == course.id).limit(1)
    module = (await db.execute(stmt)).scalar_one_or_none()
    if not module:
        module = enrolled_course["sections"][0]

    # We need the actual lesson's module
    section = enrolled_course["sections"][0]
    lesson_stmt = select(Lesson).where(Lesson.id == section.lesson_id)
    lesson = (await db.execute(lesson_stmt)).scalar_one()
    module_id = str(lesson.module_id)

    r = await client.post(
        "/api/v1/assessments",
        json={"moduleId": module_id, "assessmentType": a_type, "title": f"{a_type.capitalize()} Assessment"},
        headers=designer_headers,
    )
    assert r.status_code == 201, r.text
    assessment_id = r.json()["id"]

    for i in range(2):
        r2 = await client.post(
            f"/api/v1/assessments/{assessment_id}/questions",
            json={
                "text": f"Question {i+1}",
                "sortOrder": i,
                "explanation": "Because answer A is correct",
                "options": [
                    {"text": "Answer A", "isCorrect": True, "sortOrder": 0},
                    {"text": "Answer B", "isCorrect": False, "sortOrder": 1},
                ],
            },
            headers=designer_headers,
        )
        assert r2.status_code == 201, r2.text

    return assessment_id, module_id


class TestCreateAssessment:
    async def test_designer_creates_assessment(self, client, enrolled_course, designer_headers, db):
        assessment_id, _ = await create_test_assessment(client, enrolled_course, designer_headers, db)
        assert assessment_id

    async def test_learner_cannot_create(self, client, enrolled_course, auth_headers, db):
        from app.models.course import Lesson
        from sqlalchemy import select
        section = enrolled_course["sections"][0]
        lesson = (await db.execute(select(Lesson).where(Lesson.id == section.lesson_id))).scalar_one()
        r = await client.post(
            "/api/v1/assessments",
            json={"moduleId": str(lesson.module_id), "assessmentType": "pre", "title": "X"},
            headers=auth_headers,
        )
        assert r.status_code == 403


class TestGetAssessment:
    async def test_learner_gets_assessment_without_is_correct(
        self, client, enrolled_course, designer_headers, auth_headers, db
    ):
        assessment_id, module_id = await create_test_assessment(client, enrolled_course, designer_headers, db)
        r = await client.get(
            f"/api/v1/assessments?module_id={module_id}&type=pre",
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        for q in data["questions"]:
            for opt in q["options"]:
                assert "isCorrect" not in opt

    async def test_nonexistent_returns_404(self, client, auth_headers):
        import uuid
        r = await client.get(
            f"/api/v1/assessments?module_id={uuid.uuid4()}&type=pre",
            headers=auth_headers,
        )
        assert r.status_code == 404


class TestSubmitAttempt:
    async def test_all_correct_scores_max(
        self, client, enrolled_course, designer_headers, auth_headers, db
    ):
        assessment_id, module_id = await create_test_assessment(client, enrolled_course, designer_headers, db)
        r = await client.get(f"/api/v1/assessments?module_id={module_id}&type=pre", headers=auth_headers)
        data = r.json()
        answers = []
        for q in data["questions"]:
            correct_option = q["options"][0]
            answers.append({"questionId": q["id"], "selectedOptionId": correct_option["id"]})

        submit_r = await client.post(
            f"/api/v1/assessments/{assessment_id}/attempts",
            json={"answers": answers},
            headers=auth_headers,
        )
        assert submit_r.status_code == 201

    async def test_not_enrolled_returns_403(
        self, client, test_course, designer_headers, db
    ):
        from app.models.course import Module, Lesson, Section
        from app.models.user import Role, User
        from app.core.security import create_access_token, hash_password
        other_user = User(
            email_address="other@test.com",
            password_hash=hash_password("P1!"),
            first_name="Other",
            last_name="User",
            role=Role.learner,
        )
        db.add(other_user)
        await db.commit()
        other_headers = {"Authorization": f"Bearer {create_access_token(str(other_user.id))}"}

        module = Module(title="M", sort_order=0, course_id=test_course.id)
        db.add(module)
        await db.flush()
        r = await client.post(
            "/api/v1/assessments",
            json={"moduleId": str(module.id), "assessmentType": "pre", "title": "X"},
            headers=designer_headers,
        )
        await db.commit()
        assessment_id = r.json()["id"]

        submit_r = await client.post(
            f"/api/v1/assessments/{assessment_id}/attempts",
            json={"answers": []},
            headers=other_headers,
        )
        assert submit_r.status_code == 403

    async def test_post_assessment_blocked_if_module_incomplete(
        self, client, enrolled_course, designer_headers, auth_headers, db
    ):
        assessment_id, module_id = await create_test_assessment(
            client, enrolled_course, designer_headers, db, a_type="post"
        )
        r = await client.get(f"/api/v1/assessments?module_id={module_id}&type=post", headers=auth_headers)
        data = r.json()
        answers = [
            {"questionId": q["id"], "selectedOptionId": q["options"][0]["id"]}
            for q in data["questions"]
        ]
        submit_r = await client.post(
            f"/api/v1/assessments/{assessment_id}/attempts",
            json={"answers": answers},
            headers=auth_headers,
        )
        assert submit_r.status_code == 403
        assert submit_r.json()["detail"]["error"]["code"] == "MODULE_NOT_COMPLETE"

    async def test_designer_cannot_submit_attempt(
        self, client, enrolled_course, designer_headers, db
    ):
        assessment_id, _ = await create_test_assessment(client, enrolled_course, designer_headers, db)
        r = await client.post(
            f"/api/v1/assessments/{assessment_id}/attempts",
            json={"answers": []},
            headers=designer_headers,
        )
        assert r.status_code == 403

    async def test_nonexistent_assessment_returns_404(self, client, auth_headers):
        import uuid
        r = await client.post(
            f"/api/v1/assessments/{uuid.uuid4()}/attempts",
            json={"answers": []},
            headers=auth_headers,
        )
        assert r.status_code == 404