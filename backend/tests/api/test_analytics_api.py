"""API tests for the analytics endpoints (Story 7.1 AC1-AC3, AC5, AC6).

Covers: designer + admin → 200 + camelCase on all three endpoints; learner → 403;
unauthenticated → 401/403; unknown course/section → 404; empty-course heatmap → empty
sections (no 500); empty-section detail → zeros + insufficientData True. Follows the
existing tests/api/ pattern (auth_headers / designer_headers / admin_headers fixtures).
"""

import uuid

import pytest

from app.models.course import ContentBlock, Course, Lesson, Module, Section
from app.models.enrollment import Enrollment
from app.models.section_progress import SectionProgress

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/analytics"


async def _seed_course(db, test_user, *, with_progress=True):
    course = Course(title="Analytics Course", is_published=True)
    db.add(course)
    await db.flush()
    module = Module(title="M", sort_order=0, course_id=course.id)
    db.add(module)
    await db.flush()
    lesson = Lesson(title="L", sort_order=0, module_id=module.id)
    db.add(lesson)
    await db.flush()
    sections = []
    for i in range(2):
        s = Section(title=f"S{i}", sort_order=i, lesson_id=lesson.id)
        db.add(s)
        await db.flush()
        sections.append(s)
    db.add(
        ContentBlock(
            block_type="text",
            content={"text": "Para"},
            sort_order=0,
            section_id=sections[0].id,
        )
    )
    enr = Enrollment(user_id=test_user.id, course_id=course.id)
    db.add(enr)
    await db.flush()
    if with_progress:
        db.add(
            SectionProgress(
                user_id=test_user.id,
                section_id=sections[0].id,
                enrollment_id=enr.id,
                affect_states=["engaged", "engaged", "confused"],
                time_spent_seconds=60,
            )
        )
    await db.commit()
    return course, sections


# ── overview ────────────────────────────────────────────────────────────────────

async def test_overview_designer_200_camelcase(client, db, test_user, designer_headers):
    course, _ = await _seed_course(db, test_user)
    resp = await client.get(f"{BASE}/courses/{course.id}/overview", headers=designer_headers)
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "totalLearners",
        "completionRate",
        "averageEngagementScore",
        "confusionHotspotCount",
        "sampleCount",
        "confidence",
        "insufficientData",
    ):
        assert key in body
    assert body["totalLearners"] == 1


async def test_overview_admin_200(client, db, test_user, admin_headers):
    course, _ = await _seed_course(db, test_user)
    resp = await client.get(f"{BASE}/courses/{course.id}/overview", headers=admin_headers)
    assert resp.status_code == 200


async def test_overview_learner_403(client, db, test_user, auth_headers):
    course, _ = await _seed_course(db, test_user)
    resp = await client.get(f"{BASE}/courses/{course.id}/overview", headers=auth_headers)
    assert resp.status_code == 403


async def test_overview_unauthenticated_401_or_403(client, db, test_user):
    course, _ = await _seed_course(db, test_user)
    resp = await client.get(f"{BASE}/courses/{course.id}/overview")
    assert resp.status_code in (401, 403)


async def test_overview_unknown_course_404(client, designer_headers):
    resp = await client.get(f"{BASE}/courses/{uuid.uuid4()}/overview", headers=designer_headers)
    assert resp.status_code == 404


# ── heatmap ─────────────────────────────────────────────────────────────────────

async def test_heatmap_designer_200_ordered_camelcase(client, db, test_user, designer_headers):
    course, sections = await _seed_course(db, test_user)
    resp = await client.get(
        f"{BASE}/courses/{course.id}/affect-heatmap", headers=designer_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["courseId"] == str(course.id)
    rows = body["sections"]
    assert [r["sectionTitle"] for r in rows] == ["S0", "S1"]
    assert "engagedPct" in rows[0]
    assert "insufficientData" in rows[0]
    # S1 had no progress -> zeros + insufficientData True
    assert rows[1]["sampleCount"] == 0
    assert rows[1]["insufficientData"] is True


async def test_heatmap_admin_200(client, db, test_user, admin_headers):
    course, _ = await _seed_course(db, test_user)
    resp = await client.get(
        f"{BASE}/courses/{course.id}/affect-heatmap", headers=admin_headers
    )
    assert resp.status_code == 200


async def test_heatmap_learner_403(client, db, test_user, auth_headers):
    course, _ = await _seed_course(db, test_user)
    resp = await client.get(
        f"{BASE}/courses/{course.id}/affect-heatmap", headers=auth_headers
    )
    assert resp.status_code == 403


async def test_heatmap_empty_course_no_crash(client, db, designer_headers):
    course = Course(title="Empty", is_published=True)
    db.add(course)
    await db.commit()
    await db.refresh(course)
    resp = await client.get(
        f"{BASE}/courses/{course.id}/affect-heatmap", headers=designer_headers
    )
    assert resp.status_code == 200
    assert resp.json()["sections"] == []


async def test_heatmap_unknown_course_404(client, designer_headers):
    resp = await client.get(
        f"{BASE}/courses/{uuid.uuid4()}/affect-heatmap", headers=designer_headers
    )
    assert resp.status_code == 404


# ── section detail ──────────────────────────────────────────────────────────────

async def test_section_detail_designer_200_camelcase(client, db, test_user, designer_headers):
    course, sections = await _seed_course(db, test_user)
    resp = await client.get(
        f"{BASE}/sections/{sections[0].id}/detail", headers=designer_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "sectionId",
        "sectionTitle",
        "affectDistribution",
        "temporalDistribution",
        "keyInsights",
        "content",
        "sampleCount",
        "confidence",
        "insufficientData",
    ):
        assert key in body
    assert "engagedPct" in body["affectDistribution"]
    assert "mostTriggeredAdaptationType" in body["keyInsights"]
    assert len(body["content"]) == 1
    assert body["content"][0]["text"] == "Para"


async def test_section_detail_admin_200(client, db, test_user, admin_headers):
    course, sections = await _seed_course(db, test_user)
    resp = await client.get(
        f"{BASE}/sections/{sections[0].id}/detail", headers=admin_headers
    )
    assert resp.status_code == 200


async def test_section_detail_learner_403(client, db, test_user, auth_headers):
    course, sections = await _seed_course(db, test_user)
    resp = await client.get(
        f"{BASE}/sections/{sections[0].id}/detail", headers=auth_headers
    )
    assert resp.status_code == 403


async def test_section_detail_empty_section_zeros(client, db, test_user, designer_headers):
    course, sections = await _seed_course(db, test_user, with_progress=False)
    resp = await client.get(
        f"{BASE}/sections/{sections[1].id}/detail", headers=designer_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sampleCount"] == 0
    assert body["insufficientData"] is True
    assert body["affectDistribution"]["engagedPct"] == 0.0


async def test_section_detail_unknown_section_404(client, designer_headers):
    resp = await client.get(
        f"{BASE}/sections/{uuid.uuid4()}/detail", headers=designer_headers
    )
    assert resp.status_code == 404
