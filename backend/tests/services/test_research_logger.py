"""Tests for hardened research emit (Story 4.7 AC2/AC5)."""

import pytest

from app.services import research_logger


@pytest.fixture(autouse=True)
def _reset():
    research_logger._reset_sequences()
    yield
    research_logger._reset_sequences()


@pytest.mark.asyncio
async def test_emit_assigns_monotonic_sequence_per_session(monkeypatch):
    published: list[dict] = []

    async def fake_stream_add(stream, value):
        published.append(value)
        return "1-0"

    monkeypatch.setattr(research_logger.redis_service, "stream_add", fake_stream_add)

    for _ in range(3):
        await research_logger.emit({"event_type": "affect_classified", "session_id": "s1"})
    await research_logger.emit({"event_type": "affect_classified", "session_id": "s2"})

    s1_seqs = [e["sequence_number"] for e in published if e["session_id"] == "s1"]
    s2_seqs = [e["sequence_number"] for e in published if e["session_id"] == "s2"]
    assert s1_seqs == [1, 2, 3]      # monotonic within session
    assert s2_seqs == [1]            # isolated per session


@pytest.mark.asyncio
async def test_emit_degrades_when_stream_add_raises(monkeypatch):
    async def boom(stream, value):
        raise RuntimeError("redis down")

    monkeypatch.setattr(research_logger.redis_service, "stream_add", boom)
    # Must not raise — structlog backstop (NFR22)
    await research_logger.emit({"event_type": "cycle_completed", "session_id": "s1"})


@pytest.mark.asyncio
async def test_emit_never_raises_on_bad_event(monkeypatch):
    async def ok(stream, value):
        return None

    monkeypatch.setattr(research_logger.redis_service, "stream_add", ok)
    await research_logger.emit({})  # missing everything — still must not raise


# ── Migration 021: the content-coordinate projection ────────────────────────────


def test_content_coords_projects_course_and_section():
    coords = research_logger.content_coords({
        "topic": "Generics", "lesson": "Type Systems", "body": "...",
        "course_id": "c1", "section_id": "sec1", "lesson_id": "l1", "module_id": "m1",
    })
    assert coords == {"course_id": "c1", "section_id": "sec1"}


def test_content_coords_omits_block_id():
    """An affect cycle happens on a SECTION. Only the REST routes acting on one block (quiz
    responses) can name a block, and they stamp it themselves."""
    coords = research_logger.content_coords(
        {"course_id": "c1", "section_id": "sec1", "block_id": "blk1"}
    )
    assert "block_id" not in coords


def test_content_coords_of_unknown_section_is_empty():
    """`content_context_service.build` returns {} for a missing or unknown section. The event
    must then carry NO coordinate rather than a row of nulls, so `IS NOT NULL` stays a
    meaningful filter for "events that happened somewhere in the course"."""
    assert research_logger.content_coords({}) == {}
    assert research_logger.content_coords(None) == {}


def test_content_coords_drops_null_members():
    """A section with no parent module resolves a section_id but no course_id. Half a
    coordinate is still better than none, and the missing half stays absent."""
    assert research_logger.content_coords(
        {"section_id": "sec1", "course_id": None}
    ) == {"section_id": "sec1"}


@pytest.mark.asyncio
async def test_emit_preserves_content_coordinates_at_top_level(monkeypatch):
    """Same contract as phase/group (Story 6.5): coordinates must reach the worker at the TOP
    level, not buried in `payload`, or `research_event_service._row` cannot column them."""
    published: list[dict] = []

    async def fake_stream_add(stream, value):
        published.append(value)
        return "1-0"

    monkeypatch.setattr(research_logger.redis_service, "stream_add", fake_stream_add)

    await research_logger.emit({
        "event_type": "adaptation_delivered",
        "session_id": "s1",
        "course_id": "c1",
        "section_id": "sec1",
        "payload": {"action": "show_hint"},
    })

    assert published[0]["course_id"] == "c1"
    assert published[0]["section_id"] == "sec1"


class TestEmittersAreTotal:
    """Both emitters promise in their docstrings that they never raise. They could.

    Each wrapped its body in `except Exception: logger.exception(...)` -- and the handler uses the
    same logger that just failed. On a console whose encoding cannot represent a character in the
    event (a Windows cp1252 stdout and the "→" the router puts in its reason string), the handler
    hit the identical UnicodeEncodeError and it propagated: out of `emit_trace`, out of the
    instrumented graph node, and out of the request as a 500. Observability took the cycle down,
    which is the one thing NFR22 says it must not do.
    """

    def test_emit_trace_survives_a_logger_that_always_raises(self, monkeypatch):
        from app.services import trace

        class ExplodingLogger:
            def debug(self, *a, **kw):
                raise UnicodeEncodeError("charmap", "x", 0, 1, "no")

            def exception(self, *a, **kw):
                raise UnicodeEncodeError("charmap", "x", 0, 1, "no")

        monkeypatch.setattr(trace, "logger", ExplodingLogger())
        monkeypatch.setattr(trace.settings, "MONITOR_ENABLED", True)

        trace.emit_trace("node_completed", node="learner_profiler", reason="a → b")

    async def test_emit_survives_a_logger_that_always_raises(self, monkeypatch):
        from app.services import research_logger

        class ExplodingLogger:
            def info(self, *a, **kw):
                raise UnicodeEncodeError("charmap", "x", 0, 1, "no")

            def exception(self, *a, **kw):
                raise UnicodeEncodeError("charmap", "x", 0, 1, "no")

        monkeypatch.setattr(research_logger, "logger", ExplodingLogger())

        await research_logger.emit({
            "event_type": "learner_profile_updated",
            "session_id": "s",
            "payload": {"reason": "a → b"},
        })
