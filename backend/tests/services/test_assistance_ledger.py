"""The assistance ledger: one durable row per intervention (migration 023).

`research_events` already records the intervention chain and remains the immutable research
record. This covers the queryable projection the product reads from — written at delivery,
updated when the learner responds, and updated again when they next answer a question.

The outcome columns record an ASSOCIATION, never a cause, and the tests here are written to hold
that line: they assert what was recorded, not that the help worked.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.assistance_event import AssistanceEvent
from app.services import assistance_service

pytestmark = pytest.mark.asyncio

LEARNER = uuid.uuid4()


async def _deliver(db, adaptation_id="adapt-1", **overrides):
    kwargs = dict(
        adaptation_id=adaptation_id,
        learner_id=LEARNER,
        session_id="s1",
        cycle_number=4,
        action_type="show_hint",
        delivered=True,
        hint_text="Try comparing the two cases side by side.",
        variant="hint",
        urgency="medium",
        rationale="Learner has shown sustained confusion on this section.",
        affect_state="confused",
        affect_source="behavioral",
        affect_confidence=0.8123,
        gate_reason="ok",
        generated=True,
        fallback=False,
        phase="phase_b",
        group="adaptive",
    )
    kwargs.update(overrides)
    return await assistance_service.record_delivery(db, **kwargs)


async def _row(db, adaptation_id):
    return (
        await db.execute(
            select(AssistanceEvent).where(AssistanceEvent.adaptation_id == adaptation_id)
        )
    ).scalar_one()


class TestDelivery:

    async def test_records_what_the_learner_was_shown(self, db):
        await _deliver(db)
        row = await _row(db, "adapt-1")

        assert row.action_type == "show_hint"
        assert row.hint_text == "Try comparing the two cases side by side."
        assert row.affect_state == "confused"
        assert row.affect_confidence == 0.8123
        assert row.delivered_at is not None
        assert row.delivery_failed is False

    async def test_records_the_strategists_reason_separately_from_the_hint(self, db):
        """The rationale describes the learner in the third person and is INTERNAL. It is stored
        apart from `hint_text` so a learner-facing surface cannot render it by accident."""
        await _deliver(db)
        row = await _row(db, "adapt-1")

        assert "sustained confusion" in row.rationale
        assert row.rationale != row.hint_text

    async def test_a_failed_delivery_is_a_distinct_fact(self, db):
        """An offer the gate produced and the learner never received is different from one never
        produced, and different again from one dismissed. All three must be countable."""
        await _deliver(db, adaptation_id="adapt-failed", delivered=False)
        row = await _row(db, "adapt-failed")

        assert row.delivery_failed is True
        assert row.delivered_at is None

    async def test_records_whether_an_llm_or_the_fallback_wrote_it(self, db):
        """Production has no GPU quota, so the strategist serves its rule map. A surface that
        hid this would report the fine-tuned agent's behaviour when showing the fallback's."""
        await _deliver(db, adaptation_id="adapt-fb", generated=False, fallback=True,
                       fallback_reason="vllm_timeout")
        row = await _row(db, "adapt-fb")

        assert row.generated is False
        assert row.fallback is True
        assert row.fallback_reason == "vllm_timeout"

    async def test_missing_identity_is_skipped_not_raised(self, db):
        """Recording help must never break delivering it."""
        assert await assistance_service.record_delivery(
            db, adaptation_id="", learner_id=LEARNER, session_id="s1",
            cycle_number=1, action_type="show_hint", delivered=True,
        ) is None

    async def test_coordinates_accept_strings_from_the_event_envelope(self, db):
        """Coordinates arrive as strings on the WebSocket path and as UUIDs from route code."""
        course, section = uuid.uuid4(), uuid.uuid4()
        await _deliver(db, adaptation_id="adapt-coord",
                       course_id=str(course), section_id=str(section))
        row = await _row(db, "adapt-coord")

        assert row.course_id == course
        assert row.section_id == section

    async def test_an_unparseable_coordinate_costs_the_coordinate_not_the_row(self, db):
        await _deliver(db, adaptation_id="adapt-bad", section_id="not-a-uuid")
        row = await _row(db, "adapt-bad")

        assert row.section_id is None
        assert row.action_type == "show_hint"


class TestInteraction:

    async def test_records_what_the_learner_did_with_it(self, db):
        await _deliver(db)
        await assistance_service.record_interaction(
            db, adaptation_id="adapt-1", interaction="dismissed"
        )
        row = await _row(db, "adapt-1")

        assert row.interaction == "dismissed"
        assert row.interacted_at is not None

    async def test_unknown_id_is_ignored_not_an_error(self, db):
        """The id is client-supplied, and a response can legitimately arrive for a delivery whose
        ledger write failed."""
        assert await assistance_service.record_interaction(
            db, adaptation_id="never-existed", interaction="accepted"
        ) is None


class TestOutcome:

    async def test_records_the_answer_given_while_the_help_was_on_screen(self, db):
        await _deliver(db)
        attempt_id = uuid.uuid4()

        await assistance_service.resolve_outcome(
            db, adaptation_id="adapt-1", attempt_id=attempt_id, is_correct=True
        )
        await db.commit()
        row = await _row(db, "adapt-1")

        assert row.outcome_attempt_id == attempt_id
        assert row.outcome_is_correct is True
        assert row.outcome_resolved_at is not None

    async def test_only_the_first_answer_counts(self, db):
        """Overwriting would silently convert "wrong after the hint, right two tries later" into
        "right after the hint" — flattering, and false."""
        await _deliver(db)
        await assistance_service.resolve_outcome(
            db, adaptation_id="adapt-1", attempt_id=uuid.uuid4(), is_correct=False
        )
        await db.commit()
        await assistance_service.resolve_outcome(
            db, adaptation_id="adapt-1", attempt_id=uuid.uuid4(), is_correct=True
        )
        await db.commit()

        assert (await _row(db, "adapt-1")).outcome_is_correct is False

    async def test_an_unresolved_outcome_is_null_not_false(self, db):
        """Null means "no answer recorded yet". False would mean "answered wrongly", and
        conflating them would make every un-followed-up hint look like a failed one."""
        await _deliver(db)
        row = await _row(db, "adapt-1")

        assert row.outcome_is_correct is None
        assert row.outcome_resolved_at is None


class TestReads:

    async def test_learner_history_is_newest_first(self, db):
        for i in range(3):
            await _deliver(db, adaptation_id=f"adapt-{i}")

        rows = await assistance_service.for_learner(db, learner_id=LEARNER)
        assert len(rows) == 3
        assert rows == sorted(rows, key=lambda r: r.created_at, reverse=True)

    async def test_learner_history_is_scoped_to_the_learner(self, db):
        await _deliver(db, adaptation_id="mine")
        await _deliver(db, adaptation_id="theirs", learner_id=uuid.uuid4())

        rows = await assistance_service.for_learner(db, learner_id=LEARNER)
        assert [r.adaptation_id for r in rows] == ["mine"]

    async def test_section_read_returns_every_intervention_there(self, db):
        section = uuid.uuid4()
        await _deliver(db, adaptation_id="in-section", section_id=section)
        await _deliver(db, adaptation_id="elsewhere", section_id=uuid.uuid4())

        rows = await assistance_service.for_section(db, section_id=section)
        assert [r.adaptation_id for r in rows] == ["in-section"]


class TestTextsShownInSection:
    """The read behind "do not say the same thing twice"."""

    async def _record(self, db, *, learner_id, section_id, text):
        import uuid as uuid_mod

        from app.models.assistance_event import AssistanceEvent

        db.add(
            AssistanceEvent(
                adaptation_id=str(uuid_mod.uuid4()),
                learner_id=learner_id,
                section_id=section_id,
                action_type="show_hint",
                hint_text=text,
                affect_state="confused",
                affect_confidence=0.9,
            )
        )
        await db.commit()

    async def test_returns_only_this_learners_messages(self, db, test_user, test_designer):
        import uuid as uuid_mod

        from app.services import assistance_service

        section = uuid_mod.uuid4()
        await self._record(db, learner_id=test_designer.id, section_id=section, text="Theirs")
        await self._record(db, learner_id=test_user.id, section_id=section, text="Mine")

        found = await assistance_service.texts_shown_in_section(
            db, learner_id=test_user.id, section_id=section
        )
        assert found == ["Mine"]

    async def test_returns_only_this_sections_messages(self, db, test_user):
        """A hint about other material is not a repetition — it is unrelated."""
        import uuid as uuid_mod

        from app.services import assistance_service

        here, elsewhere = uuid_mod.uuid4(), uuid_mod.uuid4()
        await self._record(db, learner_id=test_user.id, section_id=here, text="Here")
        await self._record(db, learner_id=test_user.id, section_id=elsewhere, text="Elsewhere")

        found = await assistance_service.texts_shown_in_section(
            db, learner_id=test_user.id, section_id=here
        )
        assert found == ["Here"]

    async def test_drops_empty_text(self, db, test_user):
        """A blank line in the prompt spends tokens telling the model nothing."""
        import uuid as uuid_mod

        from app.services import assistance_service

        section = uuid_mod.uuid4()
        await self._record(db, learner_id=test_user.id, section_id=section, text="   ")
        await self._record(db, learner_id=test_user.id, section_id=section, text="Real")

        found = await assistance_service.texts_shown_in_section(
            db, learner_id=test_user.id, section_id=section
        )
        assert found == ["Real"]

    async def test_respects_the_cap(self, db, test_user):
        import uuid as uuid_mod

        from app.services import assistance_service

        section = uuid_mod.uuid4()
        for i in range(6):
            await self._record(db, learner_id=test_user.id, section_id=section, text=f"m{i}")

        found = await assistance_service.texts_shown_in_section(
            db, learner_id=test_user.id, section_id=section, limit=3
        )
        assert len(found) == 3

    async def test_empty_when_nothing_was_shown(self, db, test_user):
        import uuid as uuid_mod

        from app.services import assistance_service

        found = await assistance_service.texts_shown_in_section(
            db, learner_id=test_user.id, section_id=uuid_mod.uuid4()
        )
        assert found == []
