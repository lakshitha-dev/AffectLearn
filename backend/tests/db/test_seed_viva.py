"""The viva demonstration seed: the course each demo step relies on, and a learner who starts fresh.

The course tests pin the shape the demonstration is scripted around (an easy opener with no
authored `harder` text, a range() section with two quizzes, an exercise and a `simpler` variant, a
while-loop section with a diagram), because a content edit that dropped one of them would still
seed cleanly and only fail in front of the examiners.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select, text

import app.db.seed_viva as seed
from app.core.security import create_access_token
from app.db.demo_content import python_loops
from app.db.demo_content.people import DESIGNER
from app.models.assessment import Assessment
from app.models.course import ContentBlock, Course, Lesson, Module, Section
from app.models.enrollment import Enrollment
from app.models.research_event import ResearchEvent
from app.models.study_group import StudyGroup
from app.models.user import Role, User

pytestmark = pytest.mark.asyncio

LEARNER_PW = "Viva-learner-1"


@pytest.fixture(autouse=True)
async def enforce_foreign_keys(db):
    """Check foreign keys the way Postgres does (see `test_seed_demo.py`)."""
    await db.execute(text("PRAGMA foreign_keys=ON"))
    yield
    await db.rollback()
    await db.execute(text("PRAGMA foreign_keys=OFF"))


async def _seed(db) -> dict:
    report = await seed.seed_viva(db, learner_password=LEARNER_PW)
    await db.commit()
    return report


async def _learner(db) -> User:
    return (await db.execute(
        select(User).where(User.email_address == seed.LEARNER["email_address"])
    )).scalar_one()


async def _sections(db) -> dict[str, Section]:
    rows = (await db.execute(
        select(Section).join(Lesson).join(Module).join(Course)
        .where(Course.title == python_loops.TITLE).order_by(Section.sort_order)
    )).scalars().all()
    return {s.title: s for s in rows}


async def _blocks(db, section: Section, variant: str = "original") -> list[str]:
    """The section's block kinds in order, with a Mermaid code block reported as "mermaid"."""
    rows = (await db.execute(
        select(ContentBlock).where(ContentBlock.section_id == section.id,
                                   ContentBlock.variant_key == variant)
        .order_by(ContentBlock.sort_order)
    )).scalars().all()
    kinds = []
    for b in rows:
        kind = getattr(b.block_type, "value", b.block_type)
        kinds.append("mermaid" if kind == "code" and b.content.get("language") == "mermaid"
                     else kind)
    return kinds


# ── the course ──────────────────────────────────────────────────────────────


async def test_creates_one_published_demo_course(db):
    report = await _seed(db)
    assert report["course"] is True

    course = (await db.execute(select(Course).where(Course.title == python_loops.TITLE))).scalar_one()
    assert course.is_demo and course.is_published
    assert course.published_version_id is not None
    assert course.created_by is None  # no demo designer in this database

    assert list(await _sections(db)) == [python_loops.WHY, python_loops.FOR_RANGE,
                                         python_loops.WHILE]


async def test_each_section_has_what_its_demo_step_needs(db):
    await _seed(db)
    sections = await _sections(db)

    # The opener: easy, one quiz, and no authored challenge, so the model writes it.
    why = sections[python_loops.WHY]
    assert (await _blocks(db, why)).count("quiz") == 1
    assert await _blocks(db, why, "harder") == []

    # range(): two quizzes and an exercise for the stuck ladder, and an authored breakdown.
    rng = sections[python_loops.FOR_RANGE]
    blocks = await _blocks(db, rng)
    assert blocks.count("quiz") == 2 and blocks.count("exercise") == 1
    assert await _blocks(db, rng, "simpler") == ["text"]

    # while: the richer block types.
    loops = await _blocks(db, sections[python_loops.WHILE])
    assert {"mermaid", "table", "quiz", "exercise"} <= set(loops)


async def test_pre_and_post_checks_are_matched_pairs(db):
    await _seed(db)
    checks = {}
    for a in (await db.execute(select(Assessment))).scalars():
        await db.refresh(a, ["questions"])
        checks[a.assessment_type] = a
    assert set(checks) == {"pre", "post"}

    def pairs(a: Assessment) -> list[str]:
        return [q.explanation.split("|")[0] for q in sorted(a.questions, key=lambda q: q.sort_order)]

    assert pairs(checks["pre"]) == pairs(checks["post"]) and len(pairs(checks["pre"])) == 3
    # Same constructs, different items: a repeated item would measure recall, not learning.
    assert not {q.text for q in checks["pre"].questions} & {q.text for q in checks["post"].questions}


async def test_the_course_belongs_to_the_demo_designer_when_she_exists(db):
    anjali = User(email_address=DESIGNER["email_address"], password_hash="!unusable",
                  first_name="Anjali", last_name="Jayasinghe", role=Role.course_designer,
                  email_verified=True, is_demo=True)
    db.add(anjali)
    await db.commit()

    await _seed(db)
    course = (await db.execute(select(Course).where(Course.title == python_loops.TITLE))).scalar_one()
    assert course.created_by == anjali.id


# ── the learner ─────────────────────────────────────────────────────────────


async def test_the_learner_starts_fresh_in_the_adaptive_group(db):
    report = await _seed(db)
    assert report["learner"] is True

    learner = await _learner(db)
    assert learner.role == Role.learner
    assert learner.email_verified and learner.is_active and learner.is_demo
    assert learner.consent_given_at is None  # so the first login goes through onboarding
    group = (await db.execute(
        select(StudyGroup.group).where(StudyGroup.user_id == learner.id))).scalar_one()
    assert group == "adaptive"
    assert (await db.execute(
        select(func.count(Enrollment.id)).where(Enrollment.user_id == learner.id)
    )).scalar_one() == 0


async def test_the_learner_can_log_in_and_sees_the_course(client, db, test_course):
    await _seed(db)
    response = await client.post("/api/v1/auth/login", json={
        "emailAddress": seed.LEARNER["email_address"], "password": LEARNER_PW})
    assert response.status_code == 200, response.text

    learner = await _learner(db)
    headers = {"Authorization": f"Bearer {create_access_token(str(learner.id))}"}
    titles = {c["title"] for c in
              (await client.get("/api/v1/courses", headers=headers)).json()["items"]}
    assert python_loops.TITLE in titles


async def test_running_it_again_writes_nothing(db):
    await _seed(db)
    again = await _seed(db)
    assert again == {"course": False, "learner": False, "counts": {}}
    assert (await db.execute(
        select(func.count(Course.id)).where(Course.title == python_loops.TITLE)
    )).scalar_one() == 1


# ── reset ───────────────────────────────────────────────────────────────────


async def test_reset_recreates_a_fresh_learner_and_keeps_everything_else(db, test_user):
    await _seed(db)
    used = await _learner(db)
    course = (await db.execute(select(Course).where(Course.title == python_loops.TITLE))).scalar_one()
    # A rehearsal: onboarding done, enrolled, and research recorded.
    used.consent_given_at = datetime.now(timezone.utc)
    db.add(Enrollment(id=uuid.uuid4(), user_id=used.id, course_id=course.id, status="active"))
    now_ms = int(time.time() * 1000)
    for who in (used.id, test_user.id):
        db.add(ResearchEvent(event_type="behavioral_affect_detected", learner_id=str(who),
                             session_id="s", cycle_number=1, timestamp=now_ms))
    await db.commit()
    used_id = used.id
    db.expunge_all()

    removed = await seed.reset_learner(db)
    report = await seed.seed_viva(db, learner_password=LEARNER_PW)
    await db.commit()
    assert removed["users"] == 1 and removed["enrollments"] == 1
    assert removed["research_events"] == 1
    assert report == {"course": False, "learner": True,
                      "counts": {"study_groups": 1, "users": 1}}

    fresh = await _learner(db)
    assert fresh.id != used_id and fresh.consent_given_at is None
    assert (await db.execute(select(func.count(Enrollment.id)))).scalar_one() == 0
    # The course and the real learner's research are untouched.
    assert (await db.execute(
        select(func.count(Course.id)).where(Course.title == python_loops.TITLE)
    )).scalar_one() == 1
    remaining = (await db.execute(select(ResearchEvent.learner_id))).scalars().all()
    assert remaining == [str(test_user.id)]


async def test_reset_without_a_learner_removes_nothing(db):
    assert await seed.reset_learner(db) == {}


async def test_dry_run_writes_nothing(db, tmp_path):
    """The command line rolls back unless --confirm is given."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'viva.db'}"
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.models.base import Base

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    await seed._run(url, reset=False, confirm=False, learner_password=LEARNER_PW)

    engine = create_async_engine(url)
    async with engine.connect() as conn:
        assert (await conn.execute(select(func.count(User.id)))).scalar_one() == 0
        assert (await conn.execute(select(func.count(Course.id)))).scalar_one() == 0
    await engine.dispose()


async def test_a_password_is_required_to_write():
    with pytest.raises(SystemExit):
        seed.main(["--database-url", "sqlite+aiosqlite:///:memory:", "--confirm",
                   "--learner-password", ""])
