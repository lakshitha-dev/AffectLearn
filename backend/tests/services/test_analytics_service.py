"""Unit tests for the analytics aggregation service (Story 7.1 AC1-AC4, AC6).

Seeds a course hierarchy (modules/lessons/sections with sort_order), enrollments, and
section_progress rows with explicit affect_states, then asserts the aggregation math:
distribution tallies/percentages, overview totals/completion/engagement/hotspot count,
heatmap ordering + ~100 sums + zero-observation handling, section detail distribution /
temporal bins / insights / content annotations, and the insufficient-data threshold flips
the flag and excludes thin sections from the hotspot count.
"""

import uuid

import pytest

from app.models.course import ContentBlock, Course, Lesson, Module, Section
from app.models.enrollment import Enrollment
from app.models.research_event import ResearchEvent
from app.models.section_progress import SectionProgress
from app.models.user import Role, User
from app.services import analytics_service

pytestmark = pytest.mark.asyncio


async def _make_user(db, email, role=Role.learner):
    user = User(
        email_address=email,
        password_hash="x",
        first_name="A",
        last_name="B",
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


async def _build_course(db, *, n_sections=3):
    """Course with 1 module, 1 lesson, n sections (ordered). Returns (course, sections)."""
    course = Course(title="C", is_published=True)
    db.add(course)
    await db.flush()
    module = Module(title="M", sort_order=0, course_id=course.id)
    db.add(module)
    await db.flush()
    lesson = Lesson(title="L", sort_order=0, module_id=module.id)
    db.add(lesson)
    await db.flush()
    sections = []
    for i in range(n_sections):
        s = Section(title=f"S{i}", sort_order=i, lesson_id=lesson.id)
        db.add(s)
        await db.flush()
        sections.append(s)
    return course, sections


async def _enroll(db, user, course):
    enr = Enrollment(user_id=user.id, course_id=course.id)
    db.add(enr)
    await db.flush()
    return enr


async def _progress(db, user, enrollment, section, affect_states, time_spent=None):
    db.add(
        SectionProgress(
            user_id=user.id,
            section_id=section.id,
            enrollment_id=enrollment.id,
            affect_states=affect_states,
            time_spent_seconds=time_spent,
        )
    )
    await db.flush()


# ── affect_distribution_for_sections ────────────────────────────────────────────

async def test_distribution_tallies_and_percentages(db):
    course, sections = await _build_course(db, n_sections=1)
    u1 = await _make_user(db, "d1@t.com")
    u2 = await _make_user(db, "d2@t.com")
    enr1 = await _enroll(db, u1, course)
    enr2 = await _enroll(db, u2, course)
    # Per-learner basis: u1 shows engaged+confused (counts once each), u2 shows bored.
    # Verbose repetition by u1 must NOT skew the section (engaged logged twice -> still 1).
    await _progress(db, u1, enr1, sections[0], ["engaged", "engaged", "confused"])
    await _progress(db, u2, enr2, sections[0], ["bored"])
    await db.commit()

    dist = await analytics_service.affect_distribution_for_sections(db, [sections[0].id])
    entry = dist[sections[0].id]
    # sample_count = distinct learners observed.
    assert entry["sample_count"] == 2
    pct = entry["percentages"]
    # learners-with-state / learners-observed (=2): engaged 1/2, confused 1/2, bored 1/2.
    assert pct["engaged"] == 50.0
    assert pct["confused"] == 50.0
    assert pct["bored"] == 50.0
    assert pct["frustrated"] == 0.0


async def test_distribution_tolerates_none_and_empty(db):
    course, sections = await _build_course(db, n_sections=2)
    u1 = await _make_user(db, "n1@t.com")
    enr1 = await _enroll(db, u1, course)
    await _progress(db, u1, enr1, sections[0], None)
    await db.commit()

    dist = await analytics_service.affect_distribution_for_sections(
        db, [s.id for s in sections]
    )
    assert dist[sections[0].id]["sample_count"] == 0
    assert dist[sections[1].id]["sample_count"] == 0
    assert dist[sections[0].id]["percentages"]["engaged"] == 0.0


# ── course_overview ─────────────────────────────────────────────────────────────

async def test_overview_totals_completion_engagement(db):
    course, sections = await _build_course(db, n_sections=2)
    u1 = await _make_user(db, "o1@t.com")
    u2 = await _make_user(db, "o2@t.com")
    enr1 = await _enroll(db, u1, course)
    enr2 = await _enroll(db, u2, course)
    # u1 completes both sections; u2 completes one.
    await _progress(db, u1, enr1, sections[0], ["engaged", "engaged"])
    await _progress(db, u1, enr1, sections[1], ["engaged", "bored"])
    await _progress(db, u2, enr2, sections[0], ["bored", "bored"])
    await db.commit()

    ov = await analytics_service.course_overview(db, course.id)
    assert ov["total_learners"] == 2
    assert ov["completion_rate"] == 50.0  # only u1 completed all sections
    # per-learner engagement: 1 of 2 observed learners (u1) showed engaged -> 50%
    assert ov["average_engagement_score"] == 50.0
    # sample_count = distinct learners observed course-wide
    assert ov["sample_count"] == 2


async def test_overview_hotspot_count_respects_threshold(db):
    course, sections = await _build_course(db, n_sections=2)
    # Section 0: 6 distinct confused learners -> 100% confused, sufficient samples -> hotspot.
    for i in range(6):
        u = await _make_user(db, f"h{i}@t.com")
        enr = await _enroll(db, u, course)
        await _progress(db, u, enr, sections[0], ["confused"])
    # Section 1: 2 distinct confused learners -> 100% confused BUT thin -> NOT a hotspot.
    for i in range(2):
        u = await _make_user(db, f"ht{i}@t.com")
        enr = await _enroll(db, u, course)
        await _progress(db, u, enr, sections[1], ["confused"])
    await db.commit()

    ov = await analytics_service.course_overview(db, course.id)
    assert ov["confusion_hotspot_count"] == 1


async def test_overview_unknown_course_404(db):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await analytics_service.course_overview(db, uuid.uuid4())
    assert exc.value.status_code == 404


async def test_overview_empty_course_no_crash(db):
    course, _ = await _build_course(db, n_sections=0)
    await db.commit()
    ov = await analytics_service.course_overview(db, course.id)
    assert ov["total_learners"] == 0
    assert ov["completion_rate"] == 0.0
    assert ov["confusion_hotspot_count"] == 0
    assert ov["insufficient_data"] is True


# ── affect_heatmap ──────────────────────────────────────────────────────────────

async def test_heatmap_ordering_and_percentages(db):
    course, sections = await _build_course(db, n_sections=3)
    u1 = await _make_user(db, "hm1@t.com")
    enr1 = await _enroll(db, u1, course)
    await _progress(db, u1, enr1, sections[0], ["engaged"] * 5)
    await _progress(db, u1, enr1, sections[1], ["confused"] * 5)
    # sections[2] has no observations.
    await db.commit()

    hm = await analytics_service.affect_heatmap(db, course.id)
    rows = hm["sections"]
    assert [r["section_title"] for r in rows] == ["S0", "S1", "S2"]
    assert rows[0]["engaged_pct"] == 100.0
    assert round(
        rows[0]["engaged_pct"]
        + rows[0]["confused_pct"]
        + rows[0]["bored_pct"]
        + rows[0]["frustrated_pct"]
    ) == 100
    # zero-observation section -> zeros + insufficient_data True
    assert rows[2]["sample_count"] == 0
    assert rows[2]["insufficient_data"] is True
    assert rows[2]["engaged_pct"] == 0.0


async def test_heatmap_empty_course_returns_empty_list(db):
    course, _ = await _build_course(db, n_sections=0)
    await db.commit()
    hm = await analytics_service.affect_heatmap(db, course.id)
    assert hm["sections"] == []


# ── section_detail ──────────────────────────────────────────────────────────────

async def test_section_detail_distribution_temporal_insights_content(db):
    course, sections = await _build_course(db, n_sections=1)
    section = sections[0]
    db.add(
        ContentBlock(
            block_type="text",
            content={"text": "Hello paragraph"},
            sort_order=0,
            section_id=section.id,
        )
    )
    u1 = await _make_user(db, "sd1@t.com")
    enr1 = await _enroll(db, u1, course)
    await _progress(
        db, u1, enr1, section, ["confused", "engaged", "engaged"], time_spent=120
    )
    # research_events feed temporal + adaptation insights (best-effort, session/cycle-keyed)
    # — SCOPED to the section's learners via learner_id, so these must carry u1's id.
    db.add_all(
        [
            ResearchEvent(
                event_type="facial_affect_detected",
                learner_id=str(u1.id),
                session_id="s1",
                cycle_number=1,
                timestamp=1,
                payload={"affect_state": "confused"},
            ),
            ResearchEvent(
                event_type="facial_affect_detected",
                learner_id=str(u1.id),
                session_id="s1",
                cycle_number=2,
                timestamp=2,
                payload={"affect_state": "engaged"},
            ),
            ResearchEvent(
                event_type="adaptation_triggered",
                learner_id=str(u1.id),
                session_id="s1",
                cycle_number=1,
                timestamp=3,
                payload={"action": "provide_hint"},
            ),
            ResearchEvent(
                event_type="adaptation_triggered",
                learner_id=str(u1.id),
                session_id="s1",
                cycle_number=2,
                timestamp=4,
                payload={"action": "provide_hint"},
            ),
        ]
    )
    await db.commit()

    detail = await analytics_service.section_detail(db, section.id)
    assert detail["section_title"] == "S0"
    # per-learner basis: 1 learner observed
    assert detail["sample_count"] == 1
    ad = detail["affect_distribution"]
    # the single learner showed both engaged and confused -> 100% each
    assert ad["engaged_pct"] == 100.0
    assert ad["confused_pct"] == 100.0
    # temporal: fixed bin count
    assert len(detail["temporal_distribution"]) == analytics_service.TEMPORAL_BIN_COUNT
    # key insights
    assert detail["key_insights"]["most_triggered_adaptation_type"] == "provide_hint"
    assert detail["key_insights"]["average_confusion_duration_seconds"] is not None
    # content annotation: section-level distribution attached (sample_count > 0)
    assert len(detail["content"]) == 1
    block = detail["content"][0]
    assert block["text"] == "Hello paragraph"
    assert block["affect_distribution"] is not None


async def test_section_detail_is_section_scoped_no_bleed(db):
    """Two sections in DIFFERENT courses with different affect/adaptation events must NOT
    bleed into each other — temporal distribution and key insights are scoped to the section's
    own learners (regression test for the cross-course data-bleed finding)."""
    # Course A / section A: learner uA, confused affect + provide_hint adaptation.
    course_a, sections_a = await _build_course(db, n_sections=1)
    section_a = sections_a[0]
    ua = await _make_user(db, "bleedA@t.com")
    enr_a = await _enroll(db, ua, course_a)
    await _progress(db, ua, enr_a, section_a, ["confused"], time_spent=100)

    # Course B / section B: learner uB, engaged affect + simplify_content adaptation.
    course_b, sections_b = await _build_course(db, n_sections=1)
    section_b = sections_b[0]
    ub = await _make_user(db, "bleedB@t.com")
    enr_b = await _enroll(db, ub, course_b)
    await _progress(db, ub, enr_b, section_b, ["engaged"], time_spent=100)

    db.add_all(
        [
            ResearchEvent(
                event_type="facial_affect_detected",
                learner_id=str(ua.id),
                session_id="sa",
                cycle_number=1,
                timestamp=1,
                payload={"affect_state": "confused"},
            ),
            ResearchEvent(
                event_type="adaptation_triggered",
                learner_id=str(ua.id),
                session_id="sa",
                cycle_number=1,
                timestamp=2,
                payload={"action": "provide_hint"},
            ),
            ResearchEvent(
                event_type="facial_affect_detected",
                learner_id=str(ub.id),
                session_id="sb",
                cycle_number=1,
                timestamp=3,
                payload={"affect_state": "engaged"},
            ),
            ResearchEvent(
                event_type="adaptation_triggered",
                learner_id=str(ub.id),
                session_id="sb",
                cycle_number=1,
                timestamp=4,
                payload={"action": "simplify_content"},
            ),
        ]
    )
    await db.commit()

    detail_a = await analytics_service.section_detail(db, section_a.id)
    detail_b = await analytics_service.section_detail(db, section_b.id)

    # Insights must differ — each reflects only its own course's adaptation activity.
    assert detail_a["key_insights"]["most_triggered_adaptation_type"] == "provide_hint"
    assert detail_b["key_insights"]["most_triggered_adaptation_type"] == "simplify_content"
    assert (
        detail_a["key_insights"]["most_triggered_adaptation_type"]
        != detail_b["key_insights"]["most_triggered_adaptation_type"]
    )
    # Temporal distributions must differ (A has confusion, B does not).
    assert detail_a["temporal_distribution"] != detail_b["temporal_distribution"]
    assert any(b["confused_pct"] > 0 for b in detail_a["temporal_distribution"])
    assert all(b["confused_pct"] == 0 for b in detail_b["temporal_distribution"])


async def test_section_detail_empty_section_zeros(db):
    course, sections = await _build_course(db, n_sections=1)
    await db.commit()
    detail = await analytics_service.section_detail(db, sections[0].id)
    assert detail["sample_count"] == 0
    assert detail["insufficient_data"] is True
    assert detail["affect_distribution"]["engaged_pct"] == 0.0
    # no content blocks
    assert detail["content"] == []
    # temporal still returns the fixed bin count, all zero
    assert all(b["confused_pct"] == 0.0 for b in detail["temporal_distribution"])


async def test_section_detail_unknown_section_404(db):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await analytics_service.section_detail(db, uuid.uuid4())
    assert exc.value.status_code == 404


# ── confidence helper ───────────────────────────────────────────────────────────

async def test_confidence_bands():
    low = analytics_service._confidence(analytics_service.INSUFFICIENT_DATA_THRESHOLD - 1)
    assert low["confidence"] == "low"
    assert low["insufficient_data"] is True

    med = analytics_service._confidence(analytics_service.INSUFFICIENT_DATA_THRESHOLD)
    assert med["confidence"] == "medium"
    assert med["insufficient_data"] is False

    high = analytics_service._confidence(100)
    assert high["confidence"] == "high"
    assert high["insufficient_data"] is False
