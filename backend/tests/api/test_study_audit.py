"""Tests for the A/B research-integrity audit (FR50) and the phase transition log (Story 8.4).

Neither existed. The A/B page was read-only and reported no integrity checks at all, and the phase
toggle had no log — `study_phase` holds only the CURRENT phase, so "when did we move to Phase B,
and who moved it" was answerable only by querying the research event stream by hand.

The check that matters most is contamination, because it is the only one that can genuinely fail:
a control-group learner who received an adaptation is a learner whose sessions cannot be analysed
as controls, and nothing in the schema prevents it — the gate is application logic.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.models.assistance_event import AssistanceEvent
from app.models.research_event import ResearchEvent
from app.models.study_group import StudyGroup

pytestmark = pytest.mark.asyncio

AUDIT = "/api/v1/admin/study/audit"
HISTORY = "/api/v1/admin/study/phase/history"


def _check(body, check_id):
    return next(c for c in body if c["id"] == check_id)


async def _adaptation_for(db, learner_id):
    db.add(
        AssistanceEvent(
            adaptation_id=str(uuid.uuid4()),
            learner_id=learner_id,
            action_type="show_hint",
            hint_text="Here is a hint.",
            affect_state="confused",
            affect_confidence=0.9,
        )
    )
    await db.commit()


class TestTheAudit:
    async def test_a_clean_study_passes_every_check(
        self, client: AsyncClient, admin_headers, db, test_user
    ):
        db.add(StudyGroup(user_id=test_user.id, group="adaptive"))
        await db.commit()

        body = (await client.get(AUDIT, headers=admin_headers)).json()

        assert all(c["passed"] for c in body), body

    async def test_detects_a_contaminated_control_learner(
        self, client: AsyncClient, admin_headers, db, test_user
    ):
        """The one check that can genuinely fail — the gate is code, not a constraint."""
        db.add(StudyGroup(user_id=test_user.id, group="control"))
        await db.commit()
        await _adaptation_for(db, test_user.id)

        body = (await client.get(AUDIT, headers=admin_headers)).json()
        check = _check(body, "no_control_adaptations")

        assert check["passed"] is False
        assert check["count"] == 1
        assert "contaminated" in check["detail"].lower()

    async def test_an_adaptive_learner_receiving_adaptations_is_not_a_failure(
        self, client: AsyncClient, admin_headers, db, test_user
    ):
        db.add(StudyGroup(user_id=test_user.id, group="adaptive"))
        await db.commit()
        await _adaptation_for(db, test_user.id)

        body = (await client.get(AUDIT, headers=admin_headers)).json()

        assert _check(body, "no_control_adaptations")["passed"] is True

    async def test_detects_data_from_an_unassigned_learner(
        self, client: AsyncClient, admin_headers, db, test_user
    ):
        """Unassigned accounts default to `control` at read time.

        So their data would silently join the control arm rather than being excluded, which is
        why it has to be surfaced rather than ignored.
        """
        await _adaptation_for(db, test_user.id)  # no StudyGroup row at all

        body = (await client.get(AUDIT, headers=admin_headers)).json()
        check = _check(body, "no_unassigned_with_data")

        assert check["passed"] is False
        assert check["count"] == 1

    async def test_unassigned_learners_are_not_a_failure_before_locking(
        self, client: AsyncClient, admin_headers, test_user
    ):
        """Before the pilot starts, unassigned is the ordinary state, not an integrity problem."""
        body = (await client.get(AUDIT, headers=admin_headers)).json()

        check = _check(body, "all_learners_assigned")
        assert check["passed"] is True
        assert check["count"] == 1  # still counted and reported

    async def test_unassigned_learners_fail_once_assignments_are_locked(
        self, client: AsyncClient, admin_headers, db, test_user, test_designer
    ):
        """Locking means the cohorts are final, so a gap is no longer correctable."""
        from datetime import datetime, timezone

        # Somebody is assigned and locked; `test_user` is not assigned at all.
        db.add(
            StudyGroup(
                user_id=test_designer.id,
                group="adaptive",
                locked_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

        body = (await client.get(AUDIT, headers=admin_headers)).json()
        check = _check(body, "all_learners_assigned")

        assert check["passed"] is False
        assert "locked" in check["detail"].lower()

    async def test_designers_cannot_run_the_audit(self, client: AsyncClient, designer_headers):
        resp = await client.get(AUDIT, headers=designer_headers)
        assert resp.status_code == 403


async def _seed_transition(db, *, from_phase, to_phase, actor_id, timestamp, sequence):
    """Write a `phase_transition` row directly.

    `study_service.set_phase` emits through `research_logger`, which publishes to a Redis stream
    that a background worker batch-inserts from — deliberately, so the loop's latency budget never
    absorbs a synchronous write. Redis is disabled under test, so the route emits and nothing
    lands in `research_events`. Seeding the row is therefore what exercises the READER, which is
    the part that did not exist; `test_study.py` already covers that `set_phase` emits.
    """
    db.add(
        ResearchEvent(
            event_type="phase_transition",
            learner_id=None,
            session_id=None,
            cycle_number=0,
            timestamp=timestamp,
            sequence_number=sequence,
            phase=to_phase,
            group=None,
            payload={
                "from": from_phase,
                "to": to_phase,
                "transitioned_at": "2026-09-07T10:00:00+00:00",
                "actor_id": str(actor_id) if actor_id else None,
            },
        )
    )
    await db.commit()


class TestThePhaseLog:
    async def test_is_empty_before_any_transition(self, client: AsyncClient, admin_headers):
        body = (await client.get(HISTORY, headers=admin_headers)).json()
        assert body == []

    async def test_records_each_transition_with_who_made_it(
        self, client: AsyncClient, admin_headers, db, test_admin
    ):
        await _seed_transition(
            db,
            from_phase="phase_a",
            to_phase="phase_b",
            actor_id=test_admin.id,
            timestamp=1_000,
            sequence=1,
        )

        body = (await client.get(HISTORY, headers=admin_headers)).json()

        assert len(body) == 1
        entry = body[0]
        assert entry["fromPhase"] == "phase_a"
        assert entry["toPhase"] == "phase_b"
        assert entry["actorId"] == str(test_admin.id)
        # A UUID does not answer "who moved the study into Phase B".
        assert entry["actorName"]

    async def test_an_unknown_actor_still_yields_the_transition(
        self, client: AsyncClient, admin_headers, db
    ):
        """An actor deleted since the transition must not drop it — it still happened."""
        await _seed_transition(
            db,
            from_phase="phase_a",
            to_phase="phase_b",
            actor_id=uuid.uuid4(),
            timestamp=1_000,
            sequence=1,
        )

        body = (await client.get(HISTORY, headers=admin_headers)).json()

        assert len(body) == 1
        assert body[0]["actorName"] is None

    async def test_newest_first(self, client: AsyncClient, admin_headers, db, test_admin):
        await _seed_transition(
            db, from_phase="phase_a", to_phase="phase_b",
            actor_id=test_admin.id, timestamp=1_000, sequence=1,
        )
        await _seed_transition(
            db, from_phase="phase_b", to_phase="phase_a",
            actor_id=test_admin.id, timestamp=2_000, sequence=2,
        )

        body = (await client.get(HISTORY, headers=admin_headers)).json()

        assert [e["toPhase"] for e in body] == ["phase_a", "phase_b"]

    async def test_designers_cannot_read_the_log(self, client: AsyncClient, designer_headers):
        resp = await client.get(HISTORY, headers=designer_headers)
        assert resp.status_code == 403
