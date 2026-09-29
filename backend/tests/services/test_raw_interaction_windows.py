"""Raw interaction windows: stored only under consent, erased with the learner, and never a
change to what the behavioural model is given (migration 033, behavioural window schema v2)."""

import pytest
from sqlalchemy import func, select

import app.api.routes.ws as ws
from app.models.raw_interaction_window import RawInteractionWindow
from app.services import behavioral_inference, data_rights_service, raw_interaction_service

START = 1_790_000_000_000


def _window(**extra):
    events = [
        {"kind": "mouse_sample", "t_wall": START + 100 * i, "t_mono": 100.0 * i,
         "x": 400 + 3 * i, "y": 300 + 2 * i}
        for i in range(60)
    ]
    events += [
        {"kind": "mouse_click", "t_wall": START + 7_000, "t_mono": 7_000.0, "x": 500, "y": 310,
         "button": 0},
        {"kind": "key", "t_wall": START + 9_000, "t_mono": 9_000.0, "category": "alpha"},
        {"kind": "key", "t_wall": START + 9_200, "t_mono": 9_200.0, "category": "backspace"},
        {"kind": "scroll", "t_wall": START + 12_000, "t_mono": 12_000.0, "scroll_y": 400,
         "delta_y": 100, "direction": "down"},
        {"kind": "visibility", "t_wall": START + 20_000, "t_mono": 20_000.0, "state": "hidden"},
    ]
    return {
        "cycle_number": 3, "capture_started_at_wall": START,
        "capture_ended_at_wall": START + 30_000, "schema_version": 1, "events": events,
        "summary": {"mouse_sample_count": 60, "idle": False}, "dropped_events": 0,
        "section_id": "sec-1", **extra,
    }


def _v2(window):
    """The same window as a schema-v2 client sends it: click targets and research context."""
    events = [
        {**e, "target": "nav-next"} if e["kind"] == "mouse_click" else e
        for e in window["events"]
    ]
    return {
        **window, "events": events, "schema_version": 2, "page_instance_id": "pi-1",
        "viewport": {"w": 1536, "h": 730, "doc_h": 3120, "dpr": 1.25},
        "ui_events": [
            {"kind": "hover", "target": "block-1", "enter_t_wall": START + 1_000,
             "dwell_ms": 2_000},
            {"kind": "clipboard", "action": "paste", "target": "exercise-1-input",
             "t_wall": START + 15_000},
        ],
    }


def test_schema_v2_leaves_the_model_input_unchanged():
    """The deployed model must be given exactly the same 80 values for the same learner activity."""
    base = _window()
    v1 = behavioral_inference.extract_window_features(base["events"], START)
    v2 = behavioral_inference.extract_window_features(_v2(base)["events"], START)
    assert v1["features"] == v2["features"]
    assert v1["n_bins"] == 30


@pytest.mark.asyncio
async def test_record_window_stores_what_the_browser_sent(db, test_user):
    data = _v2(_window())
    ok = await raw_interaction_service.record_window(
        db, learner_id=str(test_user.id), session_id="s1", data=data,
        decision_id="d-1", received_at_ms=START + 30_050,
    )
    assert ok
    row = (await db.execute(select(RawInteractionWindow))).scalar_one()
    assert row.page_instance_id == "pi-1" and row.decision_id == "d-1"
    assert row.cycle_number == 3 and row.section_id == "sec-1"
    assert row.viewport["w"] == 1536
    assert len(row.events) == len(data["events"])
    assert row.ui_events[1] == {"kind": "clipboard", "action": "paste",
                                "target": "exercise-1-input", "t_wall": START + 15_000}
    assert row.partial is False


@pytest.mark.asyncio
async def test_record_window_never_raises_on_a_bad_learner_id(db):
    assert await raw_interaction_service.record_window(
        db, learner_id="not-a-uuid", session_id="s1", data=_window(),
        decision_id=None, received_at_ms=1,
    ) is False


async def _run_handler(monkeypatch, db, user, store_raw):
    async def fake_emit(event):
        return None

    async def no_graph(*_a, **_kw):
        raise RuntimeError("graph not under test")

    class _Graph:
        ainvoke = staticmethod(no_graph)

    monkeypatch.setattr(ws, "emit_research_event", fake_emit)
    monkeypatch.setattr(ws, "get_graph", lambda: _Graph())
    envelope = {"type": "behavioral_window", "ts": 1, "data": _v2(_window())}
    await ws._handle_behavioral_window(envelope, str(user.id), "s1", db, store_raw=store_raw)
    return (await db.execute(select(func.count(RawInteractionWindow.id)))).scalar_one()


@pytest.mark.asyncio
async def test_handler_stores_the_raw_window_only_with_consent(monkeypatch, db, test_user):
    assert await _run_handler(monkeypatch, db, test_user, store_raw=False) == 0
    assert await _run_handler(monkeypatch, db, test_user, store_raw=True) == 1


@pytest.mark.asyncio
async def test_erasure_removes_raw_windows(db, test_user):
    await raw_interaction_service.record_window(
        db, learner_id=str(test_user.id), session_id="s1", data=_window(),
        decision_id=None, received_at_ms=1,
    )
    counts = await data_rights_service.erase_learner(db, test_user.id)
    assert counts["raw_interaction_windows"] == 1
    assert (await db.execute(select(func.count(RawInteractionWindow.id)))).scalar_one() == 0
