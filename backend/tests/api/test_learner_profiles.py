"""Tests for the learner-progress endpoint (Story 4.6 AC1/AC3)."""

import uuid

import pytest


@pytest.mark.asyncio
async def test_learner_reads_own_progress_with_time_and_affect(
    client, auth_headers, test_user, enrolled_course
):
    section = enrolled_course["sections"][0]
    post = await client.post(
        "/api/v1/section-progress",
        headers=auth_headers,
        json={"sectionId": str(section.id), "timeSpentSeconds": 90, "affectStates": ["bored"]},
    )
    assert post.status_code in (200, 201)

    resp = await client.get(
        f"/api/v1/learner-profiles/{test_user.id}/progress", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["courses"][0]["completedSections"] == 1
    entry = data["sections"][0]
    assert entry["timeSpentSeconds"] == 90
    assert entry["affectStates"] == ["bored"]


@pytest.mark.asyncio
async def test_learner_cannot_read_another_learners_progress(client, auth_headers):
    resp = await client.get(
        f"/api/v1/learner-profiles/{uuid.uuid4()}/progress", headers=auth_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_designer_cannot_read_a_learners_progress(
    client, designer_headers, test_user, enrolled_course
):
    """This endpoint aggregates across EVERY course the learner is enrolled in.

    It previously answered 200 for any course designer, which handed one designer a learner's
    progress through other designers' courses — a cross-course read that no designer screen ever
    requested. Both real callers (`/progress` and the study thank-you summary) read the caller's
    own progress, so narrowing to self-or-admin costs nothing that was in use.

    A designer's legitimate need is the roster for a course they own; that is course-scoped by
    construction and belongs on its own endpoint rather than by widening this one.
    """
    resp = await client.get(
        f"/api/v1/learner-profiles/{test_user.id}/progress", headers=designer_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_read_any_learner_progress(
    client, admin_headers, test_user, enrolled_course
):
    resp = await client.get(
        f"/api/v1/learner-profiles/{test_user.id}/progress", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["courses"][0]["totalSections"] == 12


@pytest.mark.asyncio
async def test_negative_time_spent_rejected(client, auth_headers, enrolled_course):
    """M1: out-of-range time_spent is rejected (422) before it corrupts research data."""
    section = enrolled_course["sections"][2]
    resp = await client.post(
        "/api/v1/section-progress",
        headers=auth_headers,
        json={"sectionId": str(section.id), "timeSpentSeconds": -5},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_section_completion_without_extra_fields_still_works(
    client, auth_headers, enrolled_course
):
    section = enrolled_course["sections"][1]
    resp = await client.post(
        "/api/v1/section-progress", headers=auth_headers, json={"sectionId": str(section.id)}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["timeSpentSeconds"] is None
    assert body["affectStates"] is None
