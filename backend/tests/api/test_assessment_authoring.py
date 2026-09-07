"""Tests for designer-facing assessment authoring.

`POST /assessments` and `POST /{id}/questions` were role-guarded, tested and called by nothing, so
the pre/post assessments FR9 depends on could only be created by hand-crafted requests — and once
created could not be listed, corrected or removed.

The property pinned hardest is that the authoring view carries correct answers and the learner
view does not. `AssessmentOptionResponse` omits `is_correct` so a learner cannot read the answers
out of the payload of the test they are sitting; an author obviously needs them.
"""

import uuid

import pytest
from httpx import AsyncClient

from tests.api.test_assessments import create_test_assessment

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/assessments"


async def _module_id(db, enrolled_course):
    from sqlalchemy import select

    from app.models.course import Lesson

    section = enrolled_course["sections"][0]
    lesson = (
        await db.execute(select(Lesson).where(Lesson.id == section.lesson_id))
    ).scalar_one()
    return str(lesson.module_id)


class TestTheAuthoringView:
    async def test_lists_assessments_with_correct_answers(
        self, client: AsyncClient, enrolled_course, designer_headers, db
    ):
        await create_test_assessment(client, enrolled_course, designer_headers, db)
        module_id = await _module_id(db, enrolled_course)

        resp = await client.get(f"{BASE}/by-module/{module_id}", headers=designer_headers)

        assert resp.status_code == 200
        assessments = resp.json()
        assert len(assessments) == 1
        options = assessments[0]["questions"][0]["options"]
        assert any(o["isCorrect"] for o in options)

    async def test_the_learner_view_still_hides_the_answers(
        self, client: AsyncClient, enrolled_course, designer_headers, auth_headers, db
    ):
        await create_test_assessment(client, enrolled_course, designer_headers, db)
        module_id = await _module_id(db, enrolled_course)

        resp = await client.get(
            f"{BASE}?module_id={module_id}&type=pre", headers=auth_headers
        )

        assert resp.status_code == 200
        for question in resp.json()["questions"]:
            for option in question["options"]:
                assert "isCorrect" not in option

    async def test_learners_cannot_open_the_authoring_view(
        self, client: AsyncClient, enrolled_course, designer_headers, auth_headers, db
    ):
        await create_test_assessment(client, enrolled_course, designer_headers, db)
        module_id = await _module_id(db, enrolled_course)

        resp = await client.get(f"{BASE}/by-module/{module_id}", headers=auth_headers)
        assert resp.status_code == 403


class TestEditingAndRemoving:
    async def test_renames_an_assessment(
        self, client: AsyncClient, enrolled_course, designer_headers, db
    ):
        assessment_id, _ = await create_test_assessment(
            client, enrolled_course, designer_headers, db
        )

        resp = await client.put(
            f"{BASE}/{assessment_id}",
            json={"title": "Diagnostic check"},
            headers=designer_headers,
        )

        assert resp.status_code == 200
        assert resp.json()["title"] == "Diagnostic check"

    async def test_rewrites_a_question_and_its_options(
        self, client: AsyncClient, enrolled_course, designer_headers, db
    ):
        assessment_id, module_id = await create_test_assessment(
            client, enrolled_course, designer_headers, db
        )
        authored = (
            await client.get(f"{BASE}/by-module/{module_id}", headers=designer_headers)
        ).json()
        question_id = authored[0]["questions"][0]["id"]

        resp = await client.put(
            f"{BASE}/questions/{question_id}",
            json={
                "text": "A better question",
                "sortOrder": 0,
                "explanation": "Because.",
                "options": [
                    {"text": "Right", "isCorrect": True, "sortOrder": 0},
                    {"text": "Wrong", "isCorrect": False, "sortOrder": 1},
                ],
            },
            headers=designer_headers,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["text"] == "A better question"
        # Replaced wholesale, not appended to.
        assert len(body["options"]) == 2

    async def test_a_question_must_have_exactly_one_correct_option(
        self, client: AsyncClient, enrolled_course, designer_headers, db
    ):
        """Correctness is a property of the option SET, which is why they replace together."""
        assessment_id, module_id = await create_test_assessment(
            client, enrolled_course, designer_headers, db
        )
        authored = (
            await client.get(f"{BASE}/by-module/{module_id}", headers=designer_headers)
        ).json()
        question_id = authored[0]["questions"][0]["id"]

        for options in (
            [
                {"text": "A", "isCorrect": True, "sortOrder": 0},
                {"text": "B", "isCorrect": True, "sortOrder": 1},
            ],
            [
                {"text": "A", "isCorrect": False, "sortOrder": 0},
                {"text": "B", "isCorrect": False, "sortOrder": 1},
            ],
        ):
            resp = await client.put(
                f"{BASE}/questions/{question_id}",
                json={
                    "text": "Q",
                    "sortOrder": 0,
                    "explanation": None,
                    "options": options,
                },
                headers=designer_headers,
            )
            assert resp.status_code == 422

    async def test_deletes_a_question(
        self, client: AsyncClient, enrolled_course, designer_headers, db
    ):
        _, module_id = await create_test_assessment(
            client, enrolled_course, designer_headers, db
        )
        authored = (
            await client.get(f"{BASE}/by-module/{module_id}", headers=designer_headers)
        ).json()
        question_id = authored[0]["questions"][0]["id"]

        resp = await client.delete(
            f"{BASE}/questions/{question_id}", headers=designer_headers
        )
        assert resp.status_code == 204

        after = (
            await client.get(f"{BASE}/by-module/{module_id}", headers=designer_headers)
        ).json()
        assert len(after[0]["questions"]) == 1

    async def test_deletes_an_assessment(
        self, client: AsyncClient, enrolled_course, designer_headers, db
    ):
        assessment_id, module_id = await create_test_assessment(
            client, enrolled_course, designer_headers, db
        )

        resp = await client.delete(f"{BASE}/{assessment_id}", headers=designer_headers)
        assert resp.status_code == 204

        after = (
            await client.get(f"{BASE}/by-module/{module_id}", headers=designer_headers)
        ).json()
        assert after == []

    async def test_unknown_question_is_404(self, client: AsyncClient, designer_headers):
        resp = await client.delete(
            f"{BASE}/questions/{uuid.uuid4()}", headers=designer_headers
        )
        assert resp.status_code == 404


class TestAuthoringIsScopedToTheOwner:
    async def test_another_designer_cannot_edit(
        self, client: AsyncClient, enrolled_course, designer_headers, db
    ):
        from app.core.security import create_access_token, hash_password
        from app.models.user import Role, User

        assessment_id, _ = await create_test_assessment(
            client, enrolled_course, designer_headers, db
        )

        intruder = User(
            email_address="assessment-intruder@test.com",
            password_hash=hash_password("Password1!"),
            first_name="Not",
            last_name="Owner",
            role=Role.course_designer,
            email_verified=True,
        )
        db.add(intruder)
        await db.commit()
        await db.refresh(intruder)

        resp = await client.put(
            f"{BASE}/{assessment_id}",
            json={"title": "Mine now"},
            headers={"Authorization": f"Bearer {create_access_token(str(intruder.id))}"},
        )
        assert resp.status_code == 403
