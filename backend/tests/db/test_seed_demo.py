"""The seeded demo world: what it creates, that it can be removed, and that it tells its story.

The story tests matter as much as the row counts. The seed exists to show a course designer what
the analytics look like when a course has a real hotspot, so if a change to the simulation made
groupby look easy or the HTML opener look gripping, the demo would still load and would quietly
stop demonstrating anything.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

import app.db.seed_demo as seed
from app.core.security import create_access_token, hash_password
from app.db.demo_content.people import CLASS, DESIGNER, LEARNER
from app.models.assistance_event import AssistanceEvent
from app.models.course import Course, Section
from app.models.enrollment import Enrollment
from app.models.learner_profile import LearnerProfile
from app.models.quiz_attempt import QuizAttempt
from app.models.research_event import ResearchEvent
from app.models.study_group import StudyGroup
from app.models.user import Role, User
from app.services import analytics_service, content_effectiveness_service

pytestmark = pytest.mark.asyncio

LEARNER_PW = "Learner-demo-1"
DESIGNER_PW = "Designer-demo-1"


@pytest.fixture(autouse=True)
def fast_hashing(monkeypatch):
    """Hash only the two passwords anyone logs in with; bcrypt for all fourteen is slow."""
    monkeypatch.setattr(
        seed, "hash_password",
        lambda pw: hash_password(pw) if pw in (LEARNER_PW, DESIGNER_PW) else "!unusable",
    )


async def _seed(db) -> dict:
    report = await seed.seed_demo(db, learner_password=LEARNER_PW, designer_password=DESIGNER_PW)
    await db.commit()
    return report


async def _user(db, email: str) -> User:
    return (await db.execute(select(User).where(User.email_address == email))).scalar_one()


async def _course(db, title: str) -> Course:
    return (await db.execute(select(Course).where(Course.title == title))).scalar_one()


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


# ── what it creates ─────────────────────────────────────────────────────────


async def test_creates_a_designer_a_learner_and_a_class(db):
    report = await _seed(db)
    assert report["skipped"] is False

    users = (await db.execute(select(User))).scalars().all()
    assert len(users) == 2 + len(CLASS)
    assert all(u.is_demo and u.email_verified for u in users)

    designer = await _user(db, DESIGNER["email_address"])
    assert designer.role == Role.course_designer

    courses = {c.title: c for c in (await db.execute(select(Course))).scalars()}
    assert set(courses) == {"Python for Data Analysis", "Web Development Fundamentals",
                            "Database Design with SQL"}
    assert all(c.is_demo and c.created_by == designer.id for c in courses.values())
    assert courses["Database Design with SQL"].is_published is False
    assert courses["Python for Data Analysis"].published_version_id is not None
    assert courses["Web Development Fundamentals"].published_version_id is not None


async def test_the_learner_has_a_realistic_history(db):
    await _seed(db)
    nimali = await _user(db, LEARNER["email_address"])
    assert nimali.consent_given_at is not None  # otherwise the app sends her to onboarding
    assert nimali.degree_program and nimali.age_range

    progress = {
        title: pct for title, pct in (await db.execute(
            select(Course.title, Enrollment.progress_percentage)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .where(Enrollment.user_id == nimali.id)
        )).all()
    }
    assert progress == {"Web Development Fundamentals": 100.0, "Python for Data Analysis": 75.0}

    profile = (await db.execute(
        select(LearnerProfile).where(LearnerProfile.user_id == nimali.id))).scalar_one().profile
    assert profile["skill_level"] == "intermediate"  # three of four on the pre-test
    assert profile["topic_mastery"]

    group = (await db.execute(
        select(StudyGroup.group).where(StudyGroup.user_id == nimali.id))).scalar_one()
    assert group == "adaptive"  # so help works when she is used in a live demo

    # She is stuck on groupby: help was offered there, and she has not finished it.
    groupby = (await db.execute(
        select(Section).where(Section.title.like("Grouping%")))).scalar_one()
    helped = (await db.execute(select(AssistanceEvent).where(
        AssistanceEvent.learner_id == nimali.id,
        AssistanceEvent.section_id == groupby.id,
    ))).scalars().all()
    assert {h.action_type for h in helped} == {"show_hint", "show_breakdown"}


async def test_running_it_again_writes_nothing(db):
    await _seed(db)
    before = (await db.execute(select(func.count(ResearchEvent.id)))).scalar_one()
    assert (await _seed(db))["skipped"] is True
    assert (await db.execute(select(func.count(ResearchEvent.id)))).scalar_one() == before


# ── how it must behave in the live system ───────────────────────────────────


async def test_nothing_seeded_lands_in_the_monitor_window_or_expires_soon(db):
    await _seed(db)
    now_ms = int(time.time() * 1000)
    newest, oldest = (await db.execute(
        select(func.max(ResearchEvent.timestamp), func.min(ResearchEvent.timestamp)))).one()
    assert newest < now_ms - 24 * 3_600_000       # outside the monitor's 24-hour window
    assert oldest > now_ms - 80 * 86_400_000      # well inside the 90-day retention sweep


async def test_every_seeded_event_is_marked_synthetic(db):
    await _seed(db)
    payloads = (await db.execute(select(ResearchEvent.payload))).scalars().all()
    assert payloads and all(p.get("synthetic") is True for p in payloads)


async def test_no_profile_ends_mid_episode(db):
    """The gate reads the tail of `affect_history`; a seeded run of 'confused' would let the
    first live reading look like sustained confusion."""
    await _seed(db)
    for profile in (await db.execute(select(LearnerProfile.profile))).scalars():
        assert profile["affect_history"][-1] == "engaged"
        assert "ladder_rungs" not in profile  # the ladder is per session; none is carried in


async def test_control_learners_were_never_helped(db):
    await _seed(db)
    control = set((await db.execute(
        select(StudyGroup.user_id).where(StudyGroup.group == "control"))).scalars())
    helped = set((await db.execute(select(AssistanceEvent.learner_id))).scalars())
    assert control and helped and not control & helped


async def test_help_outcomes_point_at_the_attempt_that_followed(db):
    await _seed(db)
    for event in (await db.execute(select(AssistanceEvent).where(
            AssistanceEvent.outcome_attempt_id.isnot(None)))).scalars():
        attempt = await db.get(QuizAttempt, event.outcome_attempt_id)
        assert attempt.assistance_id == event.adaptation_id
        assert attempt.is_correct == event.outcome_is_correct
        assert attempt.submitted_at >= event.delivered_at
        assert event.interaction != "dismissed"


async def test_seeded_help_does_not_reuse_authored_variant_text(db):
    """The adapter will not repeat text a learner has seen in a section, so seeded help that
    reused a variant's wording would stop a live demo from serving that variant."""
    await _seed(db)
    from app.models.course import ContentBlock

    variants = {
        content["text"] for content in (await db.execute(select(ContentBlock.content).where(
            ContentBlock.variant_key != "original"))).scalars()
    }
    hints = set((await db.execute(select(AssistanceEvent.hint_text))).scalars())
    assert variants and not variants & hints


# ── the story the designer's screens tell ───────────────────────────────────


async def test_the_analytics_show_the_courses_real_hotspots(db):
    await _seed(db)
    for title, hotspot, boring in (
        ("Python for Data Analysis", "Grouping and Aggregating with groupby", None),
        ("Web Development Fundamentals", "Flexbox Layouts", "How a Web Page Is Built"),
    ):
        course = await _course(db, title)
        rows = [r for r in (await analytics_service.affect_heatmap(db, course.id))["sections"]
                if r["sample_count"] >= analytics_service.INSUFFICIENT_DATA_THRESHOLD]
        confused = {r["section_title"]: r["confused_pct"] for r in rows}
        assert max(confused, key=confused.get) == hotspot
        if boring:
            bored = {r["section_title"]: r["bored_pct"] for r in rows}
            assert max(bored, key=bored.get) == boring

        leaderboard = await content_effectiveness_service.struggle_leaderboard(db, course.id)
        assert leaderboard[0]["section_title"] == hotspot


async def test_the_overview_has_a_cohort_not_insufficient_data(db):
    await _seed(db)
    for title in ("Python for Data Analysis", "Web Development Fundamentals"):
        overview = await analytics_service.course_overview(db, (await _course(db, title)).id)
        assert overview["insufficient_data"] is False
        assert overview["total_learners"] >= analytics_service.INSUFFICIENT_DATA_THRESHOLD
        assert overview["confusion_hotspot_count"] >= 1


# ── through the API, as the two people who log in ───────────────────────────


async def test_both_demo_accounts_can_log_in(client, db):
    await _seed(db)
    for email, password in ((LEARNER["email_address"], LEARNER_PW),
                            (DESIGNER["email_address"], DESIGNER_PW)):
        response = await client.post("/api/v1/auth/login",
                                     json={"emailAddress": email, "password": password})
        assert response.status_code == 200, response.text


async def test_the_learner_sees_her_courses_and_her_help(client, db):
    await _seed(db)
    nimali = await _user(db, LEARNER["email_address"])
    courses = (await client.get("/api/v1/courses", headers=_headers(nimali))).json()["items"]
    enrolled = {c["title"]: c["enrollmentProgress"] for c in courses if c["isEnrolled"]}
    assert enrolled == {"Web Development Fundamentals": 100.0, "Python for Data Analysis": 75.0}
    assert "Database Design with SQL" not in {c["title"] for c in courses}  # a draft

    history = (await client.get("/api/v1/learners/me/assistance",
                                headers=_headers(nimali))).json()
    assert len(history) >= 6
    assert all(item["hintText"] for item in history)


async def test_the_designer_sees_her_courses_first_with_a_roster(client, db, test_admin):
    await _seed(db)
    # Someone else's course, newer than all of hers.
    db.add(Course(title="Someone else's", is_published=True, created_by=test_admin.id,
                  created_at=datetime.now(timezone.utc) - timedelta(days=1)))
    await db.commit()
    anjali = await _user(db, DESIGNER["email_address"])

    courses = (await client.get("/api/v1/courses", headers=_headers(anjali))).json()["items"]
    # Her newest published course leads, so the dashboard opens on it.
    assert courses[0]["title"] == "Python for Data Analysis"

    python = await _course(db, "Python for Data Analysis")
    roster = (await client.get(f"/api/v1/learners/courses/{python.id}/roster",
                               headers=_headers(anjali))).json()
    assert len(roster) == 1 + sum(1 for m in CLASS if m.python is not None)

    overview = await client.get(f"/api/v1/analytics/courses/{python.id}/overview",
                                headers=_headers(anjali))
    assert overview.status_code == 200
    assert overview.json()["insufficientData"] is False


# ── removal ─────────────────────────────────────────────────────────────────


async def test_reset_removes_every_demo_row_and_nothing_else(db, test_user, test_course):
    db.add(ResearchEvent(event_type="behavioral_affect_detected", learner_id=str(test_user.id),
                         session_id="real", cycle_number=1, timestamp=int(time.time() * 1000)))
    await db.commit()
    await _seed(db)

    removed = await seed.reset_demo(db)
    await db.commit()
    assert removed["users"] == 2 + len(CLASS)
    assert removed["courses"] == 3

    assert (await db.execute(select(func.count(User.id)).where(User.is_demo))).scalar_one() == 0
    assert (await db.execute(select(func.count(Course.id)).where(Course.is_demo))).scalar_one() == 0
    for model in (AssistanceEvent, QuizAttempt, LearnerProfile, StudyGroup, Enrollment):
        assert (await db.execute(select(func.count(model.id)))).scalar_one() == 0, model
    # The real learner, the real course and the real event are untouched.
    assert await db.get(User, test_user.id) is not None
    assert await db.get(Course, test_course.id) is not None
    remaining = (await db.execute(select(ResearchEvent.learner_id))).scalars().all()
    assert remaining == [str(test_user.id)]


async def test_dry_run_writes_nothing(db, monkeypatch, tmp_path):
    """The command line rolls back unless --confirm is given."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'demo.db'}"
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.models.base import Base

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    await seed._run(url, reset=False, confirm=False, learner_password=LEARNER_PW,
                    designer_password=DESIGNER_PW)

    engine = create_async_engine(url)
    async with engine.connect() as conn:
        assert (await conn.execute(select(func.count(User.id)))).scalar_one() == 0
    await engine.dispose()
