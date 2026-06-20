"""Tests for the pilot-study service (Story 6.1 AC2/AC3/AC4/AC8).

Covers group assignment (create/update unlocked, locked re-assign raises, get default
control, lock count) and the phase singleton (default phase_a, set returns {from,to,
transitioned_at}, emits `phase_transition` ONLY on a real change). `research_logger.emit`
is monkeypatched so emission is asserted without the Redis/worker pipeline.
"""

import pytest

from app.services import study_service as ss

pytestmark = pytest.mark.asyncio


@pytest.fixture
def captured_events(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(ss, "emit_research_event", fake_emit)
    return events


# ── group assignment ─────────────────────────────────────────────────────────--

async def test_assign_creates_row(db, test_user):
    row = await ss.assign_group(db, test_user.id, "adaptive")
    assert row.group == "adaptive"
    assert row.locked_at is None
    assert str(row.user_id) == str(test_user.id)


async def test_assign_updates_unlocked_row(db, test_user):
    await ss.assign_group(db, test_user.id, "adaptive")
    row = await ss.assign_group(db, test_user.id, "control")  # pre-pilot correction
    assert row.group == "control"
    assert await ss.get_group(db, test_user.id) == "control"


async def test_assign_invalid_group_raises(db, test_user):
    with pytest.raises(ss.InvalidGroupError):
        await ss.assign_group(db, test_user.id, "nonsense")


async def test_locked_reassign_raises(db, test_user):
    await ss.assign_group(db, test_user.id, "adaptive")
    locked = await ss.lock_assignments(db)
    assert locked == 1
    with pytest.raises(ss.GroupAssignmentLockedError):
        await ss.assign_group(db, test_user.id, "control")
    # The locked value is unchanged.
    assert await ss.get_group(db, test_user.id) == "adaptive"


async def test_get_group_defaults_to_control(db, test_user):
    assert await ss.get_group(db, test_user.id) == "control"


async def test_lock_assignments_counts_only_unlocked(db, test_user, test_designer):
    await ss.assign_group(db, test_user.id, "adaptive")
    first = await ss.lock_assignments(db)
    assert first == 1
    # A second lock with nothing new unlocked returns 0.
    second = await ss.lock_assignments(db)
    assert second == 0
    # A newly-assigned (unlocked) row is locked on the next call.
    await ss.assign_group(db, test_designer.id, "control")
    assert await ss.lock_assignments(db) == 1


async def test_list_assignments(db, test_user, test_designer):
    await ss.assign_group(db, test_user.id, "adaptive")
    await ss.assign_group(db, test_designer.id, "control")
    rows = await ss.list_assignments(db)
    assert len(rows) == 2


# ── phase singleton ──────────────────────────────────────────────────────────--

async def test_get_phase_defaults_to_phase_a(db):
    assert await ss.get_phase(db) == "phase_a"


async def test_get_phase_state_default(db):
    state = await ss.get_phase_state(db)
    assert state == {"phase": "phase_a", "transitioned_at": None}


async def test_set_phase_returns_from_to(db, captured_events):
    result = await ss.set_phase(db, "phase_b", actor_id="admin-1")
    assert result["from"] == "phase_a"
    assert result["to"] == "phase_b"
    assert result["transitioned_at"] is not None
    assert await ss.get_phase(db) == "phase_b"


async def test_set_phase_emits_event_on_real_change(db, captured_events):
    await ss.set_phase(db, "phase_b", actor_id="admin-1")
    transitions = [e for e in captured_events if e["event_type"] == "phase_transition"]
    assert len(transitions) == 1
    ev = transitions[0]
    assert ev["learner_id"] is None and ev["session_id"] is None
    assert ev["cycle_number"] == 0
    assert ev["payload"]["from"] == "phase_a"
    assert ev["payload"]["to"] == "phase_b"
    assert ev["payload"]["actor_id"] == "admin-1"
    assert ev["payload"]["transitioned_at"] is not None


async def test_set_phase_noop_does_not_emit(db, captured_events):
    # Setting phase_a when already phase_a (default) is a non-transition.
    result = await ss.set_phase(db, "phase_a")
    assert result["from"] == result["to"] == "phase_a"
    assert [e for e in captured_events if e["event_type"] == "phase_transition"] == []


async def test_set_phase_repeated_same_after_change_no_second_emit(db, captured_events):
    await ss.set_phase(db, "phase_b")
    await ss.set_phase(db, "phase_b")  # no-op
    transitions = [e for e in captured_events if e["event_type"] == "phase_transition"]
    assert len(transitions) == 1  # only the first (real) change emitted


async def test_set_phase_invalid_raises(db):
    with pytest.raises(ss.InvalidPhaseError):
        await ss.set_phase(db, "phase_c")
