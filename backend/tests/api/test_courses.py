"""Course content CRUD API tests."""

import uuid

from httpx import AsyncClient

from app.core.security import create_access_token

BASE = "/api/v1/courses"


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


async def _create_course(client: AsyncClient, headers: dict, **overrides) -> dict:
    payload = {"title": "Intro to Python", "description": "A beginner course"}
    payload.update(overrides)
    resp = await client.post(BASE, json=payload, headers=headers)
    assert resp.status_code == 201
    return resp.json()


async def _create_module(client: AsyncClient, headers: dict, course_id: str, sort_order: int = 0) -> dict:
    resp = await client.post(
        f"{BASE}/{course_id}/modules",
        json={"title": "Module 1", "description": "First module", "sortOrder": sort_order},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_lesson(client: AsyncClient, headers: dict, module_id: str, sort_order: int = 0) -> dict:
    resp = await client.post(
        f"{BASE}/modules/{module_id}/lessons",
        json={"title": "Lesson 1", "description": "First lesson", "sortOrder": sort_order},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_section(client: AsyncClient, headers: dict, lesson_id: str, sort_order: int = 0) -> dict:
    resp = await client.post(
        f"{BASE}/lessons/{lesson_id}/sections",
        json={"title": "Section 1", "sortOrder": sort_order},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_content_block(client: AsyncClient, headers: dict, section_id: str, sort_order: int = 0) -> dict:
    resp = await client.post(
        f"{BASE}/sections/{section_id}/content-blocks",
        json={
            "blockType": "text",
            "content": {"body": "Hello world"},
            "sortOrder": sort_order,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


async def _build_hierarchy(client: AsyncClient, headers: dict):
    """Create a full course → module → lesson → section → content_block hierarchy."""
    course = await _create_course(client, headers)
    module = await _create_module(client, headers, course["id"])
    lesson = await _create_lesson(client, headers, module["id"])
    section = await _create_section(client, headers, lesson["id"])
    block = await _create_content_block(client, headers, section["id"])
    return course, module, lesson, section, block


# --- Test 1: Create course as designer ---


async def test_create_course_as_designer(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)
    assert "id" in course
    assert course["title"] == "Intro to Python"
    assert course["description"] == "A beginner course"
    assert course["isPublished"] is False


# --- Test 2: Create course missing title (422) ---


async def test_create_course_missing_title(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    resp = await client.post(BASE, json={}, headers=headers)
    assert resp.status_code == 422


# --- Test 3: Create course as learner (403) ---


async def test_create_course_as_learner_forbidden(client: AsyncClient, test_user):
    headers = learner_headers(test_user)
    resp = await client.post(BASE, json={"title": "Test"}, headers=headers)
    assert resp.status_code == 403
    data = resp.json()
    assert data["detail"]["error"]["code"] == "FORBIDDEN"


# --- Test 4: Create course unauthenticated (401) ---


async def test_create_course_unauthenticated(client: AsyncClient):
    resp = await client.post(BASE, json={"title": "Test"})
    assert resp.status_code == 401


# --- Test 5: List courses as learner ---


async def test_list_courses_as_learner(client: AsyncClient, test_designer, test_user):
    headers_d = designer_headers(test_designer)
    # Learners only see published courses (AC1 of story 2.2).
    await _create_course(client, headers_d, title="Course A", isPublished=True)
    await _create_course(client, headers_d, title="Course B", isPublished=True)

    headers_l = learner_headers(test_user)
    resp = await client.get(BASE, headers=headers_l)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["page"] == 1
    assert "pageSize" in data
    assert len(data["items"]) == 2


# --- Test 6: Get course detail with nested modules ---


async def test_get_course_detail(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course, module, lesson, section, block = await _build_hierarchy(client, headers)

    resp = await client.get(f"{BASE}/{course['id']}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == course["id"]
    assert len(data["modules"]) == 1
    assert len(data["modules"][0]["lessons"]) == 1
    assert len(data["modules"][0]["lessons"][0]["sections"]) == 1
    assert len(data["modules"][0]["lessons"][0]["sections"][0]["contentBlocks"]) == 1


# --- Test 7: Get course not found (404) ---


async def test_get_course_not_found(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"{BASE}/{fake_id}", headers=headers)
    assert resp.status_code == 404
    data = resp.json()
    assert data["detail"]["error"]["code"] == "NOT_FOUND"


# --- Test 8: Update course as designer ---


async def test_update_course_as_designer(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)

    resp = await client.put(
        f"{BASE}/{course['id']}",
        json={"title": "Advanced Python", "isPublished": True},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Advanced Python"
    assert data["isPublished"] is True


# --- Test 9: Delete course as designer ---


async def test_delete_course_as_designer(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)

    resp = await client.delete(f"{BASE}/{course['id']}", headers=headers)
    assert resp.status_code == 204

    resp = await client.get(f"{BASE}/{course['id']}", headers=headers)
    assert resp.status_code == 404


# --- Test 10: Create module in course ---


async def test_create_module_in_course(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)
    module = await _create_module(client, headers, course["id"])

    assert "id" in module
    assert module["title"] == "Module 1"
    assert module["courseId"] == course["id"]


# --- Test 11: Create module in invalid course (404) ---


async def test_create_module_invalid_course(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"{BASE}/{fake_id}/modules",
        json={"title": "Module", "sortOrder": 0},
        headers=headers,
    )
    assert resp.status_code == 404


# --- Test 12: Create lesson in module ---


async def test_create_lesson_in_module(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)
    module = await _create_module(client, headers, course["id"])
    lesson = await _create_lesson(client, headers, module["id"])

    assert "id" in lesson
    assert lesson["title"] == "Lesson 1"
    assert lesson["moduleId"] == module["id"]


# --- Test 13: Create section in lesson ---


async def test_create_section_in_lesson(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)
    module = await _create_module(client, headers, course["id"])
    lesson = await _create_lesson(client, headers, module["id"])
    section = await _create_section(client, headers, lesson["id"])

    assert "id" in section
    assert section["title"] == "Section 1"
    assert section["lessonId"] == lesson["id"]


# --- Test 14: Create content block in section ---


async def test_create_content_block_in_section(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)
    module = await _create_module(client, headers, course["id"])
    lesson = await _create_lesson(client, headers, module["id"])
    section = await _create_section(client, headers, lesson["id"])
    block = await _create_content_block(client, headers, section["id"])

    assert "id" in block
    assert block["blockType"] == "text"
    assert block["content"] == {"body": "Hello world"}
    assert block["sectionId"] == section["id"]


# --- Test 15: Content block variant fields ---


async def test_content_block_variant_fields(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)
    module = await _create_module(client, headers, course["id"])
    lesson = await _create_lesson(client, headers, module["id"])
    section = await _create_section(client, headers, lesson["id"])
    block = await _create_content_block(client, headers, section["id"])

    assert block["variantKey"] == "original"
    assert block["variantGroup"] is not None
    # variant_group should be a valid UUID string
    uuid.UUID(block["variantGroup"])


# --- Test 16: Cascade delete course removes all children ---


async def test_cascade_delete_course(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course, module, lesson, section, block = await _build_hierarchy(client, headers)

    # Delete the course
    resp = await client.delete(f"{BASE}/{course['id']}", headers=headers)
    assert resp.status_code == 204

    # Verify course is gone
    resp = await client.get(f"{BASE}/{course['id']}", headers=headers)
    assert resp.status_code == 404

    # Verify modules listing for deleted course also 404s
    resp = await client.get(f"{BASE}/{course['id']}/modules", headers=headers)
    assert resp.status_code == 404


# --- Test 17: Sort order conflict (409) ---


async def test_sort_order_conflict(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)
    await _create_module(client, headers, course["id"], sort_order=0)

    # Create second module with same sort_order
    resp = await client.post(
        f"{BASE}/{course['id']}/modules",
        json={"title": "Module 2", "sortOrder": 0},
        headers=headers,
    )
    assert resp.status_code == 409
    data = resp.json()
    assert data["detail"]["error"]["code"] == "CONFLICT"


# --- Test 18: List modules ordered by sort_order ---


async def test_list_modules_ordered(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)

    await _create_module(client, headers, course["id"], sort_order=2)
    await _create_module(client, headers, course["id"], sort_order=0)
    await _create_module(client, headers, course["id"], sort_order=1)

    resp = await client.get(f"{BASE}/{course['id']}/modules", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    sort_orders = [m["sortOrder"] for m in data]
    assert sort_orders == [0, 1, 2]


# --- Test 19: CamelCase response ---


async def test_camel_case_response(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    await _create_course(client, headers, estimatedDurationMinutes=120)

    resp = await client.get(BASE, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    item = data["items"][0]
    # Verify camelCase keys
    assert "estimatedDurationMinutes" in item
    assert "isPublished" in item
    assert "createdAt" in item
    assert "updatedAt" in item
    # Verify snake_case keys are NOT present
    assert "estimated_duration_minutes" not in item
    assert "is_published" not in item


# --- Test 20: Existing auth tests pass (regression guard) ---
# This is verified by running the full test suite. No separate test needed here.


# --- Additional coverage ---


async def test_update_module(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)
    module = await _create_module(client, headers, course["id"])

    resp = await client.put(
        f"{BASE}/modules/{module['id']}",
        json={"title": "Updated Module"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Module"


async def test_delete_module(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)
    module = await _create_module(client, headers, course["id"])

    resp = await client.delete(f"{BASE}/modules/{module['id']}", headers=headers)
    assert resp.status_code == 204


async def test_update_lesson(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)
    module = await _create_module(client, headers, course["id"])
    lesson = await _create_lesson(client, headers, module["id"])

    resp = await client.put(
        f"{BASE}/lessons/{lesson['id']}",
        json={"title": "Updated Lesson"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Lesson"


async def test_delete_lesson(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)
    module = await _create_module(client, headers, course["id"])
    lesson = await _create_lesson(client, headers, module["id"])

    resp = await client.delete(f"{BASE}/lessons/{lesson['id']}", headers=headers)
    assert resp.status_code == 204


async def test_update_section(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)
    module = await _create_module(client, headers, course["id"])
    lesson = await _create_lesson(client, headers, module["id"])
    section = await _create_section(client, headers, lesson["id"])

    resp = await client.put(
        f"{BASE}/sections/{section['id']}",
        json={"title": "Updated Section"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Section"


async def test_delete_section(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)
    module = await _create_module(client, headers, course["id"])
    lesson = await _create_lesson(client, headers, module["id"])
    section = await _create_section(client, headers, lesson["id"])

    resp = await client.delete(f"{BASE}/sections/{section['id']}", headers=headers)
    assert resp.status_code == 204


async def test_update_content_block(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course, module, lesson, section, block = await _build_hierarchy(client, headers)

    resp = await client.put(
        f"{BASE}/content-blocks/{block['id']}",
        json={"content": {"body": "Updated text"}},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == {"body": "Updated text"}


async def test_delete_content_block(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course, module, lesson, section, block = await _build_hierarchy(client, headers)

    resp = await client.delete(f"{BASE}/content-blocks/{block['id']}", headers=headers)
    assert resp.status_code == 204


async def test_learner_cannot_delete_course(client: AsyncClient, test_designer, test_user):
    headers_d = designer_headers(test_designer)
    headers_l = learner_headers(test_user)
    course = await _create_course(client, headers_d)

    resp = await client.delete(f"{BASE}/{course['id']}", headers=headers_l)
    assert resp.status_code == 403


async def test_learner_can_read_modules(client: AsyncClient, test_designer, test_user):
    headers_d = designer_headers(test_designer)
    headers_l = learner_headers(test_user)
    # PUBLISHED — this test previously created a draft and asserted a learner could read it,
    # which documented the draft leak rather than the intended behaviour. Publishing states the
    # thing actually being checked: released content is readable.
    course = await _create_course(client, headers_d, isPublished=True)
    await _create_module(client, headers_d, course["id"])

    resp = await client.get(f"{BASE}/{course['id']}/modules", headers=headers_l)
    assert resp.status_code == 200


# --- Learner read scoping: unpublished courses are not readable by learners ---
#
# `list_courses` has always filtered to published courses for learners, but the fetch-by-id chain
# did not, so a learner holding a course UUID could pull the entire unreleased tree. These pin the
# rule at every entry point, because guarding only the course endpoint would leave five open doors.
#
# 404 rather than 403 is deliberate: "forbidden" would confirm that a course with that id exists
# and is being worked on.


async def test_learner_cannot_read_unpublished_course(
    client: AsyncClient, test_designer, test_user
):
    headers_d = designer_headers(test_designer)
    headers_l = learner_headers(test_user)
    course = await _create_course(client, headers_d)

    resp = await client.get(f"{BASE}/{course['id']}", headers=headers_l)
    assert resp.status_code == 404


async def test_learner_cannot_read_unpublished_modules(
    client: AsyncClient, test_designer, test_user
):
    headers_d = designer_headers(test_designer)
    headers_l = learner_headers(test_user)
    course = await _create_course(client, headers_d)
    await _create_module(client, headers_d, course["id"])

    resp = await client.get(f"{BASE}/{course['id']}/modules", headers=headers_l)
    assert resp.status_code == 404


async def test_learner_cannot_read_unpublished_lesson_detail(
    client: AsyncClient, test_designer, test_user
):
    """The worst of the six: this returns every content block, quiz answers included."""
    headers_d = designer_headers(test_designer)
    headers_l = learner_headers(test_user)
    course, module, lesson, section, block = await _build_hierarchy(client, headers_d)

    resp = await client.get(f"{BASE}/lessons/{lesson['id']}/detail", headers=headers_l)
    assert resp.status_code == 404


async def test_learner_cannot_read_unpublished_lessons_sections_or_blocks(
    client: AsyncClient, test_designer, test_user
):
    headers_d = designer_headers(test_designer)
    headers_l = learner_headers(test_user)
    course, module, lesson, section, block = await _build_hierarchy(client, headers_d)

    assert (
        await client.get(f"{BASE}/modules/{module['id']}/lessons", headers=headers_l)
    ).status_code == 404
    assert (
        await client.get(f"{BASE}/lessons/{lesson['id']}/sections", headers=headers_l)
    ).status_code == 404
    assert (
        await client.get(
            f"{BASE}/sections/{section['id']}/content-blocks", headers=headers_l
        )
    ).status_code == 404


async def test_designer_still_reads_unpublished_courses(
    client: AsyncClient, test_designer, test_user
):
    """The narrowing applies to learners only.

    Designers keep read access to drafts — including other designers' drafts, which the course
    list already shows them with `canEdit: false`. Narrowing that too would be a separate policy
    change, and would break the editor.
    """
    headers_d = designer_headers(test_designer)
    course, module, lesson, section, block = await _build_hierarchy(client, headers_d)

    assert (await client.get(f"{BASE}/{course['id']}", headers=headers_d)).status_code == 200
    assert (
        await client.get(f"{BASE}/lessons/{lesson['id']}/detail", headers=headers_d)
    ).status_code == 200


# --- Admin role write tests (M4: admin has same write access as designer) ---


async def test_create_course_as_admin(client: AsyncClient, test_admin):
    headers = admin_headers(test_admin)
    course = await _create_course(client, headers, title="Admin Course")
    assert "id" in course
    assert course["title"] == "Admin Course"


async def test_delete_course_as_admin(client: AsyncClient, test_designer, test_admin):
    headers_d = designer_headers(test_designer)
    headers_a = admin_headers(test_admin)
    course = await _create_course(client, headers_d)

    resp = await client.delete(f"{BASE}/{course['id']}", headers=headers_a)
    assert resp.status_code == 204


# --- H1 regression: nullable fields can be cleared via PUT ---


async def test_update_course_clears_nullable_description(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course = await _create_course(client, headers)
    assert course["description"] == "A beginner course"

    resp = await client.put(
        f"{BASE}/{course['id']}",
        json={"description": None},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["description"] is None


# --- H2 regression: invalid block_type returns 422, not 500 ---


async def test_create_content_block_invalid_type(client: AsyncClient, test_designer):
    headers = designer_headers(test_designer)
    course, module, lesson, section, _ = await _build_hierarchy(client, headers)

    resp = await client.post(
        f"{BASE}/sections/{section['id']}/content-blocks",
        json={"blockType": "video", "content": {"body": "x"}, "sortOrder": 99},
        headers=headers,
    )
    assert resp.status_code == 422
    assert len(resp.json()) == 1
