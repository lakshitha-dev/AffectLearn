"""Seeded demo accounts never reach a research surface; real learners always do.

Each test puts one demo learner and one real learner through the same surface and checks only the
real one comes out. A filter that dropped everyone would pass a test that looked at the demo
learner alone, so both are asserted every time.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

import pytest

from app.core.security import hash_password
from app.models.assistance_event import AssistanceEvent
from app.models.course import Course
from app.models.research_event import ResearchEvent
from app.models.study_group import StudyGroup
from app.models.user import Role, User
from app.services import (
    decision_review_service,
    gate_replay_service,
    monitor_export_service,
    research_export_service,
    study_audit_service,
)

pytestmark = pytest.mark.asyncio


async def _learner(db, name: str, *, demo: bool) -> User:
    user = User(
        email_address=f"{name}@{'demo.' if demo else ''}example.com",
        password_hash=hash_password("Password1!"), first_name=name, last_name="L",
        role=Role.learner, email_verified=True, is_demo=demo,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def pair(db):
    return await _learner(db, "real", demo=False), await _learner(db, "demo", demo=True)


def _event(learner: User, event_type: str = "behavioral_affect_detected", seq: int = 1,
           ts: int | None = None) -> ResearchEvent:
    return ResearchEvent(
        event_type=event_type, learner_id=str(learner.id), session_id=f"s-{learner.first_name}",
        cycle_number=seq, timestamp=ts or int(time.time() * 1000), sequence_number=seq,
        payload={"affect_state": "confused", "confidence": 0.8}, phase="phase_a", group="control",
    )


def _help(learner: User, group: str = "adaptive") -> AssistanceEvent:
    return AssistanceEvent(
        adaptation_id=f"a-{uuid.uuid4().hex[:12]}", learner_id=learner.id, action_type="show_hint",
        hint_text="Try the example again.", delivered_at=datetime.now(timezone.utc), group=group,
    )


async def test_research_export_leaves_out_demo_learners(db, pair):
    real, demo = pair
    db.add_all([_event(real), _event(demo)])
    await db.commit()

    page = await research_export_service.query_events(db)
    assert {e["learner_id"] for e in page["items"]} == {str(real.id)}
    assert page["total"] == 1

    # Asking for the demo learner by name still returns nothing: it is not research data.
    only_demo = await research_export_service.query_events(db, learner_id=str(demo.id))
    assert only_demo["total"] == 0


async def test_events_with_no_learner_are_still_exported(db, pair):
    real, _ = pair
    db.add(ResearchEvent(event_type="phase_transition", learner_id=None, session_id=None,
                         cycle_number=0, timestamp=int(time.time() * 1000), payload={}))
    db.add(_event(real))
    await db.commit()
    page = await research_export_service.query_events(db)
    assert page["total"] == 2


async def test_gap_audit_leaves_out_demo_learners(db, pair):
    real, demo = pair
    # Both sessions skip sequence 2; only the real one should be reported.
    db.add_all([_event(real, seq=1), _event(real, seq=3), _event(demo, seq=1), _event(demo, seq=3)])
    await db.commit()
    gaps = await research_export_service.gaps(db)
    assert set(gaps) == {f"s-{real.first_name}"}


async def test_monitor_csv_leaves_out_demo_learners(db, pair):
    real, demo = pair
    now = int(time.time() * 1000)
    db.add_all([_event(real, ts=now), _event(demo, ts=now)])
    await db.commit()
    text = "".join([
        chunk async for chunk in monitor_export_service.stream_csv(
            db, start_ts=now - 60_000, end_ts=now + 60_000)
    ])
    assert str(real.id) in text
    assert str(demo.id) not in text


async def test_educator_review_never_samples_a_demo_decision(db, pair):
    real, demo = pair
    mine, theirs = _help(real), _help(demo)
    db.add_all([mine, theirs])
    await db.commit()
    assert await decision_review_service.sample_ids(db) == [mine.id]
    assert await decision_review_service.reviewable_total(db) == 1


async def test_study_audit_ignores_demo_learners(db, pair):
    real, demo = pair
    # A demo CONTROL learner with help recorded, and an unassigned demo learner: either would
    # fail the audit if counted. The real learner is adaptive and clean.
    unassigned_demo = await _learner(db, "demo2", demo=True)
    db.add_all([
        StudyGroup(user_id=real.id, group="adaptive"),
        StudyGroup(user_id=demo.id, group="control"),
        _help(demo, group="control"),
        _help(unassigned_demo),
    ])
    await db.commit()

    checks = {c["id"]: c for c in await study_audit_service.audit(db)}
    assert checks["no_control_adaptations"]["passed"]
    assert checks["no_unassigned_with_data"]["passed"]
    assert checks["all_learners_assigned"]["count"] == 0


async def test_study_audit_still_catches_a_real_contaminated_control(db, pair):
    real, _ = pair
    db.add_all([StudyGroup(user_id=real.id, group="control"), _help(real, group="control")])
    await db.commit()
    checks = {c["id"]: c for c in await study_audit_service.audit(db)}
    assert not checks["no_control_adaptations"]["passed"]


async def test_gate_replay_leaves_out_demo_readings(db, pair):
    real, demo = pair
    db.add_all([_event(real), _event(demo)])
    await db.commit()
    readings, _ = await gate_replay_service._load_sessions(db)
    assert set(readings) == {f"s-{real.first_name}"}


class TestCatalogue:
    async def _courses(self, db, designer):
        real = Course(title="Real Course", is_published=True, created_by=designer.id)
        demo = Course(title="Demo Course", is_published=True, created_by=designer.id, is_demo=True)
        db.add_all([real, demo])
        await db.commit()

    async def test_a_real_learner_never_sees_a_demo_course(self, client, db, test_designer,
                                                           auth_headers):
        await self._courses(db, test_designer)
        titles = {c["title"] for c in (await client.get(
            "/api/v1/courses", headers=auth_headers)).json()["items"]}
        assert titles == {"Real Course"}

    async def test_a_demo_learner_sees_everything(self, client, db, test_designer):
        from app.core.security import create_access_token

        await self._courses(db, test_designer)
        demo = await _learner(db, "viewer", demo=True)
        headers = {"Authorization": f"Bearer {create_access_token(str(demo.id))}"}
        titles = {c["title"] for c in (await client.get(
            "/api/v1/courses", headers=headers)).json()["items"]}
        assert titles == {"Real Course", "Demo Course"}

    async def test_a_designer_sees_their_own_courses_first(self, client, db, test_designer,
                                                           test_admin, designer_headers):
        # Someone else's course, created AFTER the designer's own: newest-first alone would put
        # it on top.
        db.add_all([
            Course(title="Mine", is_published=True, created_by=test_designer.id,
                   created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            Course(title="Theirs", is_published=True, created_by=test_admin.id,
                   created_at=datetime(2026, 6, 1, tzinfo=timezone.utc)),
        ])
        await db.commit()
        items = (await client.get("/api/v1/courses", headers=designer_headers)).json()["items"]
        assert items[0]["title"] == "Mine"
