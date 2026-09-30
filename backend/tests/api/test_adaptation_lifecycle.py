"""Card lifecycle events (`adaptation_event` -> `adaptation_lifecycle` research events).

What happened to a delivered card that is not the learner's verdict on it: first visible,
re-opened, probe shown or left unanswered, how a suggested break went. They must never touch the
ledger or the delivery guard, and they need participation consent like any other capture.
"""
async def test_adaptation_event_is_recorded_as_a_lifecycle_research_event(monkeypatch):
    import app.api.routes.ws as ws

    events: list[dict] = []

    async def capture(event):
        events.append(event)

    monkeypatch.setattr(ws, "emit_research_event", capture)
    await ws._handle_adaptation_event({"type": "adaptation_event", "ts": 1, "data": {
        "adaptation_id": "ad-1", "action": "suggest_break", "event": "break_returned_early",
        "seconds_away": 120, "since_received_ms": 4000, "section_id": "sec-1", "cycle_number": 7,
    }}, "u1", "s1", "phase_b", "adaptive")
    (event,) = events
    assert event["event_type"] == "adaptation_lifecycle"
    assert event["section_id"] == "sec-1" and event["cycle_number"] == 7
    assert event["payload"] == {"adaptation_id": "ad-1", "action": "suggest_break",
                                "event": "break_returned_early", "since_received_ms": 4000,
                                "seconds_away": 120}


async def test_unknown_lifecycle_events_are_dropped(monkeypatch):
    import app.api.routes.ws as ws

    events: list[dict] = []

    async def capture(event):
        events.append(event)

    monkeypatch.setattr(ws, "emit_research_event", capture)
    await ws._handle_adaptation_event(
        {"data": {"adaptation_id": "ad-1", "event": "accepted"}}, "u1", "s1")
    await ws._handle_adaptation_event({"data": {"event": "rendered"}}, "u1", "s1")
    assert events == []


def test_lifecycle_needs_participation_consent():
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from app.services.consent import ConsentState

    withdrawn = SimpleNamespace(consent_given_at=datetime.now(timezone.utc),
                                consent_withdrawn_at=datetime.now(timezone.utc),
                                webcam_enabled=True, consent_scopes=None)
    assert ConsentState.of(withdrawn).refusal("adaptation_event") == "no_consent"
