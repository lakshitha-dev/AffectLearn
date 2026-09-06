"""The 90-day retention limit, enforced rather than promised.

The participant-facing copy states that study data is deleted within 90 days. That existed as a
sentence and not as a job, which the thesis records as a prerequisite for opening the pilot.

These cover the sweep itself. The worker that schedules it is a lifespan asyncio task following
the same pattern as `research_worker`; what matters to a participant is that the sweep deletes
the right rows and leaves the rest alone.
"""

import time
import uuid

import pytest
from sqlalchemy import func, select

from app.models.research_event import ResearchEvent
from app.models.user import Role, User
from app.services import data_rights_service

pytestmark = pytest.mark.asyncio

DAY_MS = 24 * 60 * 60 * 1000


def _event(age_days: float, learner_id: str = "u1", seq: int = 1) -> ResearchEvent:
    return ResearchEvent(
        event_type="behavioral_affect_detected",
        learner_id=learner_id,
        session_id="s1",
        cycle_number=seq,
        timestamp=int(time.time() * 1000) - int(age_days * DAY_MS),
        sequence_number=seq,
        payload={},
    )


async def _count(db) -> int:
    return (await db.execute(select(func.count(ResearchEvent.id)))).scalar_one()


async def test_deletes_events_past_the_limit(db):
    db.add_all([_event(120, seq=1), _event(95, seq=2)])
    await db.commit()

    removed = await data_rights_service.purge_research_events_older_than(db, days=90)

    assert removed == 2
    assert await _count(db) == 0


async def test_keeps_events_inside_the_limit(db):
    db.add_all([_event(1, seq=1), _event(45, seq=2), _event(89, seq=3)])
    await db.commit()

    removed = await data_rights_service.purge_research_events_older_than(db, days=90)

    assert removed == 0
    assert await _count(db) == 3


async def test_sweeps_only_what_has_expired(db):
    db.add_all([_event(200, seq=1), _event(10, seq=2)])
    await db.commit()

    await data_rights_service.purge_research_events_older_than(db, days=90)

    survivor = (await db.execute(select(ResearchEvent))).scalar_one()
    assert survivor.sequence_number == 2


async def test_an_empty_sweep_is_a_no_op(db):
    assert await data_rights_service.purge_research_events_older_than(db, days=90) == 0


async def test_the_limit_is_configurable(db):
    """The 90 in the copy is a policy number, not a constant compiled into the sweep."""
    db.add_all([_event(45, seq=1)])
    await db.commit()

    assert await data_rights_service.purge_research_events_older_than(db, days=90) == 0
    assert await data_rights_service.purge_research_events_older_than(db, days=30) == 1


async def test_retention_does_not_touch_accounts_or_progress(db):
    """Retention covers the RESEARCH record. A learner's account and their own course progress
    are theirs until they ask for erasure — quietly deleting somebody's learning history because
    a research limit expired would be a different decision made under cover of a privacy job.
    """
    user = User(
        email_address=f"retention-{uuid.uuid4().hex[:8]}@test.com",
        password_hash="x",
        first_name="R",
        last_name="T",
        role=Role.learner,
        email_verified=True,
    )
    db.add(user)
    db.add(_event(500, seq=1))
    await db.commit()

    await data_rights_service.purge_research_events_older_than(db, days=90)

    assert await db.get(User, user.id) is not None
