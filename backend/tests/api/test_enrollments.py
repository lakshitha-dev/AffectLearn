"""Course enrollment API tests."""

import uuid

from httpx import AsyncClient

from app.core.security import create_access_token

COURSES = "/api/v1/courses"
ENROLLMENTS = "/api/v1/enrollments"


# --- Helpers ---


def designer_headers(test_designer):
    token = create_access_token(str(test_designer.id))
    return {"Authorization": f"Bearer {token}"}


def admin_headers(test_admin):
    token = create_access_token(str(test_admin.id))
    return {"Authorization": f"Bearer {token}"}


def learner_headers(test_user):
    token = create_access_token(str(test_user.id))
    return {"Authorization": f"Bearer {token}"}


async def _create_course(
    client: AsyncClient, headers: dict, *, published: bool = True, **overrides
) -> dict:
    payload = {
        "title": "Intro to Python",
        "description": "A beginner course",
        "isPublished": published,
        "estimatedDurationMinutes": 60,
    }
    payload.update(overrides)
    resp = await client.post(COURSES, json=payload, headers=headers)
    assert resp.status_code == 201
    return resp.json()


async def _create_module(
    client: AsyncClient, headers: dict, course_id: str, sort_order: int = 0
) -> dict:
    resp = await client.post(
        f"{COURSES}/{course_id}/modules",
        json={"title": f"Module {sort_order}", "sortOrder": sort_order},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


# --- Enrollment creation ---


async def test_enroll_happy_path(test_client: AsyncClient, test_designer, test_user):
    h_d = designer_headers(test_designer)
    course = await _create_course(test_client, h_d)

    h_l = learner_headers(test_user)
    resp = await test_client.post(
        ENROLLMENTS, json={"courseId": course["id"]}, headers=h_l
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["courseId"] == course["id"]
    assert data["progressPercentage"] == 0.0
    assert data["status"] == "active"


async def test_enroll_duplicate_returns_409(test_client: AsyncClient, test_designer, test_user):
    h_d = designer_headers(test_designer)
    course = await _create_course(test_client, h_d)
    h_l = learner_headers(test_user)

    resp1 = await test_client.post(
        ENROLLMENTS, json={"courseId": course["id"]}, headers=h_l
    )
    assert resp1.status_code == 201

    resp2 = await test_client.post(
        ENROLLMENTS, json={"courseId": course["id"]}, headers=h_l
    )
    assert resp2.status_code == 409
    assert resp2.json()["detail"]["error"]["code"] == "ALREADY_ENROLLED"


async def test_enroll_unpublished_course_returns_404(
    test_client: AsyncClient, test_designer, test_user
):
    h_d = designer_headers(test_designer)
    course = await _create_course(test_client, h_d, published=False)
    h_l = learner_headers(test_user)

    resp = await test_client.post(
        ENROLLMENTS, json={"courseId": course["id"]}, headers=h_l
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "NOT_FOUND"


async def test_enroll_missing_course_returns_404(test_client: AsyncClient, test_user):
    h_l = learner_headers(test_user)
    fake_id = str(uuid.uuid4())
    resp = await test_client.post(
        ENROLLMENTS, json={"courseId": fake_id}, headers=h_l
    )
    assert resp.status_code == 404


async def test_enroll_unauthenticated_returns_401(test_client: AsyncClient):
    fake_id = str(uuid.uuid4())
    resp = await test_client.post(ENROLLMENTS, json={"courseId": fake_id})
    assert resp.status_code == 401


# --- RBAC ---


async def test_designer_cannot_enroll(test_client: AsyncClient, test_designer):
    """Only learners can enroll. Designers/admins are forbidden."""
    h_d = designer_headers(test_designer)
    course = await _create_course(test_client, h_d)
    resp = await test_client.post(
        ENROLLMENTS, json={"courseId": course["id"]}, headers=h_d
    )
    assert resp.status_code == 403


async def test_admin_cannot_enroll(test_client: AsyncClient, test_designer, test_admin):
    h_d = designer_headers(test_designer)
    h_a = admin_headers(test_admin)
    course = await _create_course(test_client, h_d)
    resp = await test_client.post(
        ENROLLMENTS, json={"courseId": course["id"]}, headers=h_a
    )
    assert resp.status_code == 403


# --- Listing ---


async def test_list_enrollments_empty(test_client: AsyncClient, test_user):
    h_l = learner_headers(test_user)
    resp = await test_client.get(ENROLLMENTS, headers=h_l)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


async def test_list_enrollments_includes_course_summary(
    test_client: AsyncClient, test_designer, test_user
):
    h_d = designer_headers(test_designer)
    course = await _create_course(test_client, h_d, title="Algo 101")
    await _create_module(test_client, h_d, course["id"], sort_order=0)
    await _create_module(test_client, h_d, course["id"], sort_order=1)

    h_l = learner_headers(test_user)
    await test_client.post(ENROLLMENTS, json={"courseId": course["id"]}, headers=h_l)

    resp = await test_client.get(ENROLLMENTS, headers=h_l)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["courseId"] == course["id"]
    assert item["courseTitle"] == "Algo 101"
    assert item["courseModuleCount"] == 2
    assert item["progressPercentage"] == 0.0


async def test_list_enrollments_pagination(
    test_client: AsyncClient, test_designer, test_user
):
    h_d = designer_headers(test_designer)
    h_l = learner_headers(test_user)

    course_ids = []
    for i in range(3):
        course = await _create_course(test_client, h_d, title=f"Course {i}")
        course_ids.append(course["id"])
        await test_client.post(
            ENROLLMENTS, json={"courseId": course["id"]}, headers=h_l
        )

    resp = await test_client.get(
        f"{ENROLLMENTS}?page=1&page_size=2", headers=h_l
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["page"] == 1


async def test_list_enrollments_sorted_by_last_accessed(
    test_client: AsyncClient, db_session, test_designer, test_user
):
    """Enrollments with a recent last_accessed_at appear before those without."""
    import datetime as dt
    from datetime import timezone

    from app.services import enrollment_service

    h_d = designer_headers(test_designer)
    h_l = learner_headers(test_user)

    course_a = await _create_course(test_client, h_d, title="Course A")
    course_b = await _create_course(test_client, h_d, title="Course B")

    await test_client.post(ENROLLMENTS, json={"courseId": course_a["id"]}, headers=h_l)
    await test_client.post(ENROLLMENTS, json={"courseId": course_b["id"]}, headers=h_l)

    # Touch course_b's enrollment so it has a recent last_accessed_at; course_a
    # remains NULL and must therefore sort last (NULLS LAST + DESC).
    enrollment_b = await enrollment_service.get_enrollment(
        db_session, user_id=test_user.id, course_id=uuid.UUID(course_b["id"])
    )
    assert enrollment_b is not None
    await enrollment_service.update_enrollment_progress(
        db_session,
        enrollment_id=enrollment_b.id,
        last_accessed_at=dt.datetime.now(tz=timezone.utc),
    )

    resp = await test_client.get(ENROLLMENTS, headers=h_l)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    assert items[0]["courseId"] == course_b["id"]
    assert items[1]["courseId"] == course_a["id"]


async def test_list_enrollments_unauthenticated_returns_401(test_client: AsyncClient):
    resp = await test_client.get(ENROLLMENTS)
    assert resp.status_code == 401


async def test_list_enrollments_designer_forbidden(
    test_client: AsyncClient, test_designer
):
    """Designers cannot fetch a learner enrollment listing."""
    h_d = designer_headers(test_designer)
    resp = await test_client.get(ENROLLMENTS, headers=h_d)
    assert resp.status_code == 403


# --- Status check ---


async def test_get_enrollment_status_when_enrolled(
    test_client: AsyncClient, test_designer, test_user
):
    h_d = designer_headers(test_designer)
    course = await _create_course(test_client, h_d)
    h_l = learner_headers(test_user)
    await test_client.post(ENROLLMENTS, json={"courseId": course["id"]}, headers=h_l)

    resp = await test_client.get(f"{ENROLLMENTS}/{course['id']}", headers=h_l)
    assert resp.status_code == 200
    data = resp.json()
    assert data is not None
    assert data["courseId"] == course["id"]


async def test_get_enrollment_status_when_not_enrolled(
    test_client: AsyncClient, test_designer, test_user
):
    h_d = designer_headers(test_designer)
    course = await _create_course(test_client, h_d)
    h_l = learner_headers(test_user)

    resp = await test_client.get(f"{ENROLLMENTS}/{course['id']}", headers=h_l)
    assert resp.status_code == 200
    assert resp.json() is None


# --- Course list filter / search ---


async def test_course_list_filters_unpublished_for_learner(
    test_client: AsyncClient, test_designer, test_user
):
    h_d = designer_headers(test_designer)
    await _create_course(test_client, h_d, title="Published", published=True)
    await _create_course(test_client, h_d, title="Draft", published=False)

    h_l = learner_headers(test_user)
    resp = await test_client.get(COURSES, headers=h_l)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Published"


async def test_course_list_designer_sees_all(
    test_client: AsyncClient, test_designer
):
    h_d = designer_headers(test_designer)
    await _create_course(test_client, h_d, title="Published", published=True)
    await _create_course(test_client, h_d, title="Draft", published=False)

    resp = await test_client.get(COURSES, headers=h_d)
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


async def test_course_search_matches_title_and_description(
    test_client: AsyncClient, test_designer, test_user
):
    h_d = designer_headers(test_designer)
    await _create_course(
        test_client, h_d, title="Intro to Python", description="A beginner course"
    )
    await _create_course(
        test_client, h_d, title="Advanced Rust", description="Memory safety basics"
    )

    h_l = learner_headers(test_user)
    resp = await test_client.get(f"{COURSES}?search=python", headers=h_l)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Intro to Python"

    resp = await test_client.get(f"{COURSES}?search=memory", headers=h_l)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


async def test_course_list_annotates_enrollment_for_learner(
    test_client: AsyncClient, test_designer, test_user
):
    h_d = designer_headers(test_designer)
    course_a = await _create_course(test_client, h_d, title="Enrolled course")
    course_b = await _create_course(test_client, h_d, title="Not enrolled")

    h_l = learner_headers(test_user)
    await test_client.post(
        ENROLLMENTS, json={"courseId": course_a["id"]}, headers=h_l
    )

    resp = await test_client.get(COURSES, headers=h_l)
    assert resp.status_code == 200
    items = {item["title"]: item for item in resp.json()["items"]}
    assert items["Enrolled course"]["isEnrolled"] is True
    assert items["Enrolled course"]["enrollmentProgress"] == 0.0
    assert items["Not enrolled"]["isEnrolled"] is False


async def test_course_list_module_count(
    test_client: AsyncClient, test_designer, test_user
):
    h_d = designer_headers(test_designer)
    course = await _create_course(test_client, h_d)
    await _create_module(test_client, h_d, course["id"], sort_order=0)
    await _create_module(test_client, h_d, course["id"], sort_order=1)

    h_l = learner_headers(test_user)
    resp = await test_client.get(COURSES, headers=h_l)
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["moduleCount"] == 2
