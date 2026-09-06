"""The performance channel end to end, through the same gate as the models.

The point of this suite is what it does NOT bypass. A new channel that quietly routed around the
sustain check, the cooldown or the channel-authority rule would reintroduce exactly the failure
Chapter 4 records: a weak channel acting on a confidence it had not earned, with nothing in the
record to show it was happening.
"""

import pytest

import app.api.routes.ws as ws
from app.agents import edges
from app.agents.state import AFFECT_SOURCE_PERFORMANCE

pytestmark = pytest.mark.asyncio

SECTION_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def captured_events(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(ws, "emit_research_event", fake_emit)
    return events


@pytest.fixture(autouse=True)
def grounded(monkeypatch):
    """Stand in for the cached section lookup so these exercise the CHANNEL, not the resolver."""
    from app.services import content_context_service

    async def fake_build(section_id, _db):
        if not section_id:
            return {}
        return {
            "topic": "Pointers", "lesson": "Memory", "body": "...", "difficulty": "unknown",
            "n_words": 400,
            "section_id": SECTION_ID, "course_id": "11111111-1111-1111-1111-111111111111",
        }

    monkeypatch.setattr(content_context_service, "build", fake_build)


def _window(cycle=1, **counts):
    data = {"cycle_number": cycle, "section_id": SECTION_ID}
    data.update(counts)
    return {"type": "performance_window", "ts": 1, "data": data}


async def test_a_struggling_learner_produces_a_reading(captured_events):
    await ws._handle_performance_window(
        _window(quiz_incorrect_count=3, show_answer_used=True, back_nav_count=2),
        "u1",
        "s1",
    )

    assert len(captured_events) == 1
    event = captured_events[0]
    assert event["event_type"] == "performance_signal_detected"
    assert event["payload"]["affect_state"] == "confused"
    assert event["payload"]["affect_source"] == AFFECT_SOURCE_PERFORMANCE


async def test_a_learner_doing_fine_produces_nothing(captured_events):
    """A quiet cycle stays quiet. Emitting near-zero readings would fill the record and dilute
    the sustain check the other channels depend on."""
    await ws._handle_performance_window(_window(quiz_incorrect_count=0), "u1", "s1")

    assert captured_events == []


async def test_the_reading_is_located(captured_events):
    await ws._handle_performance_window(
        _window(quiz_incorrect_count=3, show_answer_used=True), "u1", "s1"
    )

    assert captured_events[0]["section_id"] == SECTION_ID


async def test_the_record_carries_the_breakdown_not_only_a_score(captured_events):
    """What lets an analyst recompute the score under different weights from the stored record,
    rather than re-running the study."""
    await ws._handle_performance_window(
        _window(quiz_incorrect_count=3, show_answer_used=True), "u1", "s1"
    )

    payload = captured_events[0]["payload"]
    assert payload["counts"]["quiz_incorrect_count"] == 3
    assert payload["breakdown"]["revealed_answer"] > 0
    assert payload["heuristic"] is True


async def test_it_is_marked_as_its_own_detection_mode(captured_events):
    """So an analysis can separate model-driven interventions from behaviour-driven ones without
    inferring which was which after the fact."""
    await ws._handle_performance_window(
        _window(quiz_incorrect_count=3, show_answer_used=True), "u1", "s1"
    )

    assert captured_events[0]["payload"]["detection_mode"] == "performance_only"


async def test_a_malformed_window_does_not_break_the_session(captured_events):
    """Every field comes from a browser."""
    await ws._handle_performance_window(
        {"type": "performance_window", "ts": 1, "data": {"quiz_incorrect_count": "lots"}},
        "u1",
        "s1",
    )
    assert captured_events == []


class TestItDoesNotBypassTheGate:

    def test_the_channel_is_known_to_the_gate(self):
        """An unclassified source is logged as a configuration gap on EVERY cycle it is
        evaluated. Registering it is what keeps that warning meaningful."""
        assert AFFECT_SOURCE_PERFORMANCE in edges._KNOWN_AFFECT_SOURCES

    def test_it_is_advisory_by_default(self):
        """Deliberate. Chapter 4 records what happened when a weak channel was allowed to
        intervene on a confidence it had not earned, and the answer was not "measure it first".

        Shipping advisory means the gate records `channel_advisory` every time this channel WOULD
        have intervened — so its rate becomes a measurement before it becomes a behaviour. Promote
        it by adding `performance` to DECISIVE_AFFECT_SOURCES once there is pilot data.
        """
        assert AFFECT_SOURCE_PERFORMANCE not in edges.DECISIVE_AFFECT_SOURCES
        assert edges.is_decisive(AFFECT_SOURCE_PERFORMANCE) is False

    def test_it_has_its_own_confidence_floor(self):
        """Its "confidence" is a weighted count of behaviours, not a calibrated probability, so
        it does not share an operating point with either model."""
        assert edges.min_confidence_for(AFFECT_SOURCE_PERFORMANCE) == 0.60

    def test_a_withheld_cycle_records_why(self):
        """The gate logging a reason is how the facial-channel and cooldown defects were found at
        all. A new channel must be visible in the same way."""
        allowed, reason = edges.passes_adaptation_gate(
            "confused",
            0.9,
            ["confused", "confused"],
            5,
            None,
            AFFECT_SOURCE_PERFORMANCE,
        )
        assert allowed is False
        assert reason == edges.GATE_CHANNEL_ADVISORY
