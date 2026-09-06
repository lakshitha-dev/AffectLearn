"""The zero-video-storage guarantee, enforced by test rather than by inspection.

The consent screen, the privacy policy and the ethics section all state that webcam imagery never
leaves the browser as pixels and is never stored. Until now that was a property of the code path
and nothing else — the thesis records it as "a property of the code path rather than of an
automated test", with the enforcing test outstanding.

The distinction matters because the failure would be silent. Adding a LangGraph checkpointer, or
widening a research-event payload to include the whole inbound message, would persist base64
frames without breaking a single existing test. Nothing would look wrong; the guarantee would
simply stop being true.

These tests fail loudly on exactly those changes.
"""

import inspect

import pytest

from app.agents import graph as graph_module
from app.agents.state import make_initial_state
from app.models.base import Base

#: The field carrying inbound webcam data. Named once so a rename has to be deliberate.
_FRAME_FIELD = "frames_b64"


#: Columns whose names trip the heuristic below but have been inspected and do not hold imagery.
#:
#: An allowlist rather than a narrower word list, deliberately. Dropping "snapshot" from the
#: suspicious words to let `content_versions.snapshot` through would also let a future
#: `frame_snapshot` through unnoticed. Making each exception explicit means a new match still
#: fails the build and gets looked at, and the reason it was cleared is written down beside it.
_REVIEWED_NOT_IMAGERY: dict[str, str] = {
    # A JSON copy of a course's module/lesson/section/block tree, taken at publish so a
    # measurement can be checked against the content it was recorded on (migration 025).
    "content_versions.snapshot": "course content tree, not a captured image",
}


def test_no_database_column_could_hold_a_frame():
    """No table has a column whose name suggests it stores imagery.

    Blunt on purpose. The guarantee is not "we currently do not write frames", it is "there is
    nowhere to write them to", and a schema-level check is what makes the second true.
    """
    suspicious = ("frame", "image", "video", "pixel", "photo", "snapshot", "b64", "base64")
    found = [
        name
        for table, meta in Base.metadata.tables.items()
        for column in meta.columns
        if (name := f"{table}.{column.name}") not in _REVIEWED_NOT_IMAGERY
        and any(word in column.name.lower() for word in suspicious)
    ]
    assert not found, (
        f"columns that could hold webcam imagery: {found}. The platform promises frames are "
        "never stored; a column to put them in is the first step to breaking that."
    )


def test_the_agent_graph_has_no_checkpointer():
    """A checkpointer persists `AgentState` between invocations — and `AgentState.facial_payload`
    carries the base64 frames for the current cycle. Adding one would write them to disk as a
    side effect of an unrelated feature, which is why the state module carries an explicit
    warning not to.
    """
    source = inspect.getsource(graph_module)
    lowered = source.lower()
    for marker in ("checkpointer=", "memorysaver", "sqlitesaver", "postgressaver"):
        assert marker not in lowered, (
            f"the agent graph appears to configure a checkpointer ({marker!r}). "
            "AgentState.facial_payload holds base64 webcam frames; persisting state persists them."
        )


def test_frames_are_seeded_into_transient_state_only():
    """The frames reach the graph, which is necessary — the model has to see them. What must not
    happen is anything that outlives the invocation."""
    state = make_initial_state(
        learner_id="u1",
        session_id="s1",
        cycle_number=1,
        facial_payload={_FRAME_FIELD: "AAAABBBB", "frames_captured": 16},
    )
    assert state["facial_payload"][_FRAME_FIELD] == "AAAABBBB"


@pytest.mark.asyncio
async def test_a_facial_cycle_emits_no_frame_data(monkeypatch):
    """The research event for a facial cycle is built from a WHITELIST of fields. This asserts
    the whitelist has not been replaced by a spread of the inbound payload — the single most
    likely way frames would end up in the durable record.
    """
    import app.agents.nodes.affect_detection as ad
    import app.api.routes.ws as ws

    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    async def fake_detect(_data):
        return {
            "engagement_level": 2, "label": "high", "confidence": 0.8,
            "probs": [0.1, 0.1, 0.7, 0.1], "frames_used": 16,
        }

    monkeypatch.setattr(ws, "emit_research_event", fake_emit)
    monkeypatch.setattr(ad, "detect_engagement", fake_detect)

    await ws._handle_facial_features(
        {
            "type": "facial_features",
            "ts": 1,
            "data": {
                "cycle_number": 1,
                "frames_captured": 16,
                "dropped_frames": 0,
                _FRAME_FIELD: "SECRETFRAMEDATA",
            },
        },
        "u1",
        "s1",
    )

    assert events, "expected a facial_affect_detected event"
    serialised = repr(events)
    assert "SECRETFRAMEDATA" not in serialised
    assert _FRAME_FIELD not in serialised


@pytest.mark.asyncio
async def test_a_facial_cycle_still_records_what_it_should(monkeypatch):
    """The counterpart to the test above: proving frames are absent is only meaningful if the
    event is otherwise populated. An event that recorded nothing would pass the check above and
    mean nothing.
    """
    import app.agents.nodes.affect_detection as ad
    import app.api.routes.ws as ws

    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    async def fake_detect(_data):
        return {
            "engagement_level": 2, "label": "high", "confidence": 0.8,
            "probs": [0.1, 0.1, 0.7, 0.1], "frames_used": 16,
        }

    monkeypatch.setattr(ws, "emit_research_event", fake_emit)
    monkeypatch.setattr(ad, "detect_engagement", fake_detect)

    await ws._handle_facial_features(
        {
            "type": "facial_features",
            "ts": 1,
            "data": {
                "cycle_number": 7,
                "frames_captured": 16,
                "dropped_frames": 0,
                _FRAME_FIELD: "SECRETFRAMEDATA",
            },
        },
        "u1",
        "s1",
    )

    payload = events[0]["payload"]
    assert events[0]["cycle_number"] == 7
    assert payload["frames_captured"] == 16
    assert payload["affect_state"]
