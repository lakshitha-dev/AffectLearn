"""Tests for the dev-only adaptation harness.

Two properties matter more than the happy path:

  * It must be UNREACHABLE in production. It fabricates affect readings, writes to the research
    record, and pushes messages to a learner's screen.
  * It must not leave the learner's profile seeded. The gate's persistence and ladder conditions
    read the profile, so a run has to write one; if it stayed, the next GENUINE detection would
    satisfy the sustain condition on fabricated evidence. `purge_synthetic_events.py` exists
    because that already happened once.

The rest pins that a verdict is REPORTED rather than arranged away: an unreachable affect state
comes back as `state_not_actionable` with a note saying why, not as a forced delivery.
"""

import pytest

from app.agents import edges
from app.core.config import settings
from app.services import profile_service, redis_service

pytestmark = pytest.mark.asyncio

URL = "/api/v1/dev/simulate-cycle"


@pytest.fixture
def section_id(enrolled_course):
    return str(enrolled_course["sections"][0].id)


async def test_404_in_production(client, auth_headers, section_id, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    resp = await client.post(
        URL, headers=auth_headers, json={"sectionId": section_id, "affectState": "confused"}
    )
    assert resp.status_code == 404


async def test_404_in_production_regardless_of_case(
    client, auth_headers, section_id, monkeypatch
):
    # The check lowercases, so PRODUCTION / Production must not slip through.
    monkeypatch.setattr(settings, "ENVIRONMENT", "PRODUCTION")
    resp = await client.post(URL, headers=auth_headers, json={"sectionId": section_id})
    assert resp.status_code == 404


async def test_requires_a_learner(client, designer_headers, admin_headers, section_id):
    for headers in (designer_headers, admin_headers):
        resp = await client.post(URL, headers=headers, json={"sectionId": section_id})
        assert resp.status_code == 403


async def test_requires_authentication(client, section_id):
    resp = await client.post(URL, json={"sectionId": section_id})
    assert resp.status_code in (401, 403)


async def test_unknown_section_is_404(client, auth_headers):
    resp = await client.post(
        URL,
        headers=auth_headers,
        json={"sectionId": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


async def test_full_loop_reports_the_gate_verdict(client, auth_headers, section_id):
    resp = await client.post(
        URL,
        headers=auth_headers,
        json={"sectionId": section_id, "affectState": "confused", "rung": 0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "fullLoop" or body["mode"] == "full_loop"
    assert body["gateReason"] is not None
    assert body["sessionId"].startswith("devsim-")
    # The settings the verdict was reached under travel with it, so a surprising reason is
    # explicable without opening the admin page.
    assert "adaptStates" in body["gateConfig"]


async def test_seeding_satisfies_the_persistence_condition(client, auth_headers, section_id):
    # A single fabricated reading cannot clear `min_consecutive` on its own. If the harness seeded
    # the interleaved `affect_history` instead of the per-source one, this comes back
    # `not_sustained` -- which is the bug that makes a harness look broken when the gate is fine.
    resp = await client.post(
        URL,
        headers=auth_headers,
        json={
            "sectionId": section_id,
            "affectState": "confused",
            "affectSource": "behavioral_model",
            "affectConfidence": 0.95,
        },
    )
    assert resp.json()["gateReason"] != edges.GATE_NOT_SUSTAINED


async def test_low_confidence_is_reported_not_arranged_away(client, auth_headers, section_id):
    resp = await client.post(
        URL,
        headers=auth_headers,
        json={"sectionId": section_id, "affectState": "confused", "affectConfidence": 0.1},
    )
    body = resp.json()
    assert body["gateReason"] == edges.GATE_LOW_CONFIDENCE
    assert any("floor" in note for note in body["notes"])


async def test_unreachable_affect_state_says_so(client, auth_headers, section_id, monkeypatch):
    from app.services import config_service

    monkeypatch.setattr(edges, "ADAPT_STATES", ("bored", "confused"))
    config_service._reset()

    resp = await client.post(
        URL, headers=auth_headers, json={"sectionId": section_id, "affectState": "frustrated"}
    )
    body = resp.json()
    assert body["gateReason"] == edges.GATE_STATE_NOT_ACTIONABLE
    # The note is the point: a green run against a forced condition is otherwise
    # indistinguishable from a working capability.
    assert any("ADAPT_STATES" in note for note in body["notes"])
    assert any("frustrated" in note for note in body["notes"])


async def test_advisory_channel_says_so(client, auth_headers, section_id, monkeypatch):
    from app.services import config_service

    monkeypatch.setattr(edges, "DECISIVE_AFFECT_SOURCES", ("behavioral_model",))
    config_service._reset()

    resp = await client.post(
        URL,
        headers=auth_headers,
        json={
            "sectionId": section_id,
            "affectState": "confused",
            "affectSource": "facial_geometry",
        },
    )
    body = resp.json()
    assert body["gateReason"] == edges.GATE_CHANNEL_ADVISORY
    assert any("decisive" in note for note in body["notes"])


async def test_profile_is_restored_after_a_run(client, auth_headers, section_id, monkeypatch):
    """The seeded history must not outlive the request.

    Left behind, `affect_history_by_source` holds `min_consecutive` fabricated entries and the
    next genuine detection satisfies the sustain condition on top of them -- an intervention no
    real evidence supports.
    """
    store: dict[str, dict] = {}

    async def fake_get(key):
        return store.get(key)

    async def fake_set(key, value, ttl_seconds=None):
        store[key] = value

    monkeypatch.setattr(redis_service, "get_json", fake_get)
    monkeypatch.setattr(redis_service, "set_json", fake_set)

    before = {**profile_service.default_profile(), "skill_level": "advanced",
              "affect_history": ["engaged"]}
    key = None

    resp = await client.post(
        URL, headers=auth_headers, json={"sectionId": section_id, "affectState": "confused"}
    )
    assert resp.status_code == 200
    # The learner had no profile in this run, so the harness resets rather than leaves a seed.
    for k, v in store.items():
        if k.startswith("profile:learner:"):
            key = k
            assert not v.get("affect_history_by_source"), (
                "seeded per-source history survived the request"
            )
            assert v.get("affect_history") == []
    assert key is not None, "the run never wrote a profile"

    # And with an existing profile, it is the ORIGINAL that comes back, not a default.
    store[key] = before
    await client.post(
        URL, headers=auth_headers, json={"sectionId": section_id, "affectState": "confused"}
    )
    assert store[key] == before


async def test_forced_action_skips_the_gate_and_writes_nothing(
    client, auth_headers, section_id, db
):
    from sqlalchemy import func, select

    from app.models.assistance_event import AssistanceEvent

    before = (await db.execute(select(func.count()).select_from(AssistanceEvent))).scalar()
    resp = await client.post(
        URL,
        headers=auth_headers,
        json={
            "sectionId": section_id,
            "actionType": "show_breakdown",
            "text": "One step at a time.",
        },
    )
    body = resp.json()
    assert body["actionType"] == "show_breakdown"
    assert body["text"] == "One step at a time."
    assert body["gateReason"] is None
    assert body["generated"] is False
    after = (await db.execute(select(func.count()).select_from(AssistanceEvent))).scalar()
    assert after == before, "a forced push must not enter the learner's help history"


async def test_forced_action_default_text_admits_what_it_is(client, auth_headers, section_id):
    resp = await client.post(
        URL, headers=auth_headers, json={"sectionId": section_id, "actionType": "show_hint"}
    )
    text = resp.json()["text"]
    assert "ynthetic" in text and "No model" in text


async def test_forced_no_action_delivers_nothing(client, auth_headers, section_id):
    # `deliver_node` builds no message for `no_action`, and the response must say that rather
    # than report a delivery.
    resp = await client.post(
        URL, headers=auth_headers, json={"sectionId": section_id, "actionType": "no_action"}
    )
    body = resp.json()
    assert body["delivered"] is False
    assert any("not a deliverable action" in note for note in body["notes"])


async def test_no_live_socket_is_reported(client, auth_headers, section_id):
    # There is no WebSocket in these tests, so nothing can reach a screen. Silence here would
    # make "the card did not appear" indistinguishable from "the loop chose nothing".
    resp = await client.post(
        URL, headers=auth_headers, json={"sectionId": section_id, "actionType": "show_hint"}
    )
    body = resp.json()
    assert body["delivered"] is False
    assert any("no live websocket" in note.lower() for note in body["notes"])


async def test_withheld_arm_is_reachable(client, auth_headers, section_id, monkeypatch):
    from app.services import config_service

    # The conftest turns withholding off for every other test; this one is about the draw.
    monkeypatch.setattr(edges, "ADAPT_WITHHOLD_RATE", 0.35)
    config_service._reset()

    resp = await client.post(
        URL,
        headers=auth_headers,
        json={"sectionId": section_id, "affectState": "confused", "arm": "withheld"},
    )
    assert resp.json()["gateReason"] == edges.GATE_WITHHELD_RANDOM


async def test_delivered_arm_avoids_the_draw(client, auth_headers, section_id, monkeypatch):
    from app.services import config_service

    monkeypatch.setattr(edges, "ADAPT_WITHHOLD_RATE", 0.35)
    config_service._reset()

    resp = await client.post(
        URL,
        headers=auth_headers,
        json={"sectionId": section_id, "affectState": "confused", "arm": "delivered"},
    )
    assert resp.json()["gateReason"] != edges.GATE_WITHHELD_RANDOM


async def test_events_are_marked_synthetic(client, auth_headers, section_id, monkeypatch):
    """Every research event a run emits must carry the mark, at the emission point.

    Without it the rows are indistinguishable from genuine learner cycles -- `research_events` has
    no origin column -- and cleaning them up needs a session-id list someone remembered to keep.
    """
    captured: list[dict] = []

    from app.services import research_logger

    async def fake_stream_add(stream, value):
        captured.append(value)
        return "1-1"

    monkeypatch.setattr(research_logger.redis_service, "stream_add", fake_stream_add)

    await client.post(
        URL, headers=auth_headers, json={"sectionId": section_id, "affectState": "confused"}
    )
    assert captured, "the run emitted no research events at all"
    for event in captured:
        assert (event.get("payload") or {}).get("synthetic") is True, event.get("event_type")


async def test_the_mark_does_not_leak_outside_the_run(monkeypatch):
    from app.services import research_logger

    assert research_logger.is_synthetic_run() is False
    with research_logger.synthetic_run():
        assert research_logger.is_synthetic_run() is True
    assert research_logger.is_synthetic_run() is False


async def test_engaged_is_reported_as_intended_not_as_a_gap(client, auth_headers, section_id):
    # `engaged` is absent from ADAPT_STATES by design -- the system leaves a learner who is
    # working well alone, and there is no ladder for it. Reporting that the same way as a
    # DISABLED state turns correct behaviour into a warning.
    resp = await client.post(
        URL, headers=auth_headers, json={"sectionId": section_id, "affectState": "engaged"}
    )
    body = resp.json()
    assert body["gateReason"] == edges.GATE_STATE_NOT_ACTIONABLE
    assert any("by design" in note for note in body["notes"])
    assert not any("show_encouragement" in note for note in body["notes"])
