"""Tests for the in-process observability bus and the research_logger tap."""

import asyncio

from app.services.monitor_bus import MonitorBus


async def test_publish_appends_to_ring_and_caps():
    bus = MonitorBus(ring_size=5)
    for i in range(7):
        bus.publish({"event_type": "e", "session_id": "s", "i": i})
    recent = bus.recent()
    assert len(recent) == 5            # ring buffer caps at maxlen
    assert recent[-1]["i"] == 6        # newest retained
    assert recent[0]["i"] == 2         # oldest two dropped


async def test_subscriber_receives_published_event():
    bus = MonitorBus(ring_size=10)
    q = bus.subscribe()
    bus.publish({"event_type": "x", "session_id": "s"})
    ev = await asyncio.wait_for(q.get(), timeout=1.0)
    assert ev["event_type"] == "x"
    bus.unsubscribe(q)
    assert bus.subscriber_count() == 0


async def test_recent_filters_by_session():
    bus = MonitorBus(ring_size=10)
    bus.publish({"session_id": "a", "event_type": "e"})
    bus.publish({"session_id": "b", "event_type": "e"})
    only_a = bus.recent(session_id="a")
    assert only_a and all(e["session_id"] == "a" for e in only_a)
    assert bus.session_ids() == ["b", "a"]  # most-recent first


async def test_full_subscriber_drops_oldest_not_raises():
    bus = MonitorBus(ring_size=100)
    q = bus.subscribe(maxsize=2)
    for i in range(5):
        bus.publish({"event_type": "e", "i": i})  # never raises despite full queue
    # Queue holds the 2 most-recent after drop-oldest behaviour.
    drained = [q.get_nowait()["i"] for _ in range(q.qsize())]
    assert drained == [3, 4]


async def test_emit_reaches_bus_even_when_redis_disabled(monkeypatch):
    from app.services import redis_service, research_logger
    from app.services.monitor_bus import monitor_bus

    monkeypatch.setattr(redis_service, "_disabled", True, raising=False)
    await research_logger.emit(
        {
            "event_type": "behavioral_affect_detected",
            "learner_id": "L",
            "session_id": "redis-down-sess",
            "cycle_number": 1,
            "timestamp": 1,
            "payload": {},
        }
    )
    evs = monitor_bus.recent(session_id="redis-down-sess")
    assert any(
        e["event_type"] == "behavioral_affect_detected" and e.get("category") == "domain"
        for e in evs
    )
