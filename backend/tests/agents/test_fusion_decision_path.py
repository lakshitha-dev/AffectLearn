"""Fusion must drive the LIVE decision, not just the research log.

The bug these guard: `_maybe_fuse` computed a fused estimate, emitted it as a
`multimodal_affect_detected` event, and returned None. Nothing wrote it back, so every
pedagogical decision came from ONE model however multimodal the logs looked. The claim
"the system fuses two modalities" was true of the logging and false of the behaviour.

The load-bearing assertion is `test_fused_state_reaches_the_decision`: it fails if the fused
value is computed and discarded, which is exactly the shape of the original defect.
"""

import numpy as np
import pytest

from app.agents.nodes.affect_detection import (
    _resolve_detection_mode,
    affect_detection_node,
    fusion_drives_decision,
)
from app.agents.state import make_initial_state
from app.services import fusion_buffer


@pytest.fixture(autouse=True)
def _clean_buffer():
    fusion_buffer._reset()
    yield
    fusion_buffer._reset()


def _behavioural_result(p_confused: float) -> dict:
    """A behavioural result in BEHAVIORAL_CLASS_ORDER = (engaged, bored, confused, frustrated)."""
    probs = [1.0 - p_confused, 0.0, p_confused, 0.0]
    idx = int(np.argmax(probs))
    return {"affect_index": idx, "label": ["engaged", "bored", "confused", "frustrated"][idx],
            "confidence": float(probs[idx]), "probs": probs}


def _facial_result(p_confused: float) -> dict:
    probs = [1.0 - p_confused, p_confused]
    idx = int(np.argmax(probs))
    return {"engagement_level": idx, "label": ["not_confused", "confused"][idx],
            "confidence": float(probs[idx]), "probs": probs}


# --- mode resolution -------------------------------------------------------------------

def test_mode_is_multimodal_only_when_a_counterpart_is_seeded():
    single = make_initial_state(learner_id="u", session_id="s", cycle_number=1,
                               behavioral_payload={"events": []})
    assert _resolve_detection_mode(single) == "behavioral_only"

    paired = make_initial_state(learner_id="u", session_id="s", cycle_number=1,
                               behavioral_payload={"events": []},
                               counterpart_inference=_facial_result(0.8),
                               counterpart_modality="facial")
    assert _resolve_detection_mode(paired) == "multimodal"


def test_flag_off_reverts_to_single_modality(monkeypatch):
    """One env var must undo this, because the measured evidence mildly disfavours fusing."""
    monkeypatch.setenv("FUSION_DRIVES_DECISION", "0")
    assert fusion_drives_decision() is False
    paired = make_initial_state(learner_id="u", session_id="s", cycle_number=1,
                               behavioral_payload={"events": []},
                               counterpart_inference=_facial_result(0.9),
                               counterpart_modality="facial")
    assert _resolve_detection_mode(paired) == "behavioral_only"


@pytest.mark.parametrize("value,expected", [("1", True), ("", True), ("0", False),
                                            ("false", False), ("no", False), ("true", True)])
def test_flag_parsing(monkeypatch, value, expected):
    monkeypatch.setenv("FUSION_DRIVES_DECISION", value)
    assert fusion_drives_decision() is expected


# --- the decision path -----------------------------------------------------------------

async def test_fused_state_reaches_the_decision(monkeypatch):
    """THE regression guard. Two channels disagreeing must change the written affect_state.

    Behaviour says engaged at 0.95; the facial counterpart says confused at 0.95. A
    confidence-weighted fusion of two equally confident, opposing votes must NOT simply pass the
    behavioural label through — if it does, the fused value was computed and discarded.
    """
    monkeypatch.setattr("app.agents.nodes.affect_detection.predict_from_window",
                        lambda events, started: _behavioural_result(0.05))
    state = make_initial_state(learner_id="u", session_id="s", cycle_number=1,
                               behavioral_payload={"events": [], "capture_started_at_wall": 0},
                               counterpart_inference=_facial_result(0.95),
                               counterpart_modality="facial")
    out = await affect_detection_node(state)

    assert out["detection_mode"] == "multimodal"
    assert out["fusion_applied"] is True
    assert "fusion_weights" in out
    # The behavioural branch alone would have written engaged/0.95.
    assert not (out["affect_state"] == "engaged" and out["affect_confidence"] == pytest.approx(0.95)), \
        "affect_state is the raw behavioural result — the fused value was discarded"


async def test_agreement_produces_that_state(monkeypatch):
    monkeypatch.setattr("app.agents.nodes.affect_detection.predict_from_window",
                        lambda events, started: _behavioural_result(0.88))
    state = make_initial_state(learner_id="u", session_id="s", cycle_number=2,
                               behavioral_payload={"events": [], "capture_started_at_wall": 0},
                               counterpart_inference=_facial_result(0.80),
                               counterpart_modality="facial")
    out = await affect_detection_node(state)
    assert out["affect_state"] == "confused"
    assert out["fusion_applied"] is True


async def test_unpaired_cycle_is_untouched(monkeypatch):
    monkeypatch.setattr("app.agents.nodes.affect_detection.predict_from_window",
                        lambda events, started: _behavioural_result(0.77))
    state = make_initial_state(learner_id="u", session_id="s", cycle_number=3,
                               behavioral_payload={"events": [], "capture_started_at_wall": 0})
    out = await affect_detection_node(state)
    assert out["detection_mode"] == "behavioral_only"
    assert out.get("fusion_applied") is not True
    assert out["affect_state"] == "confused"
    assert out["affect_confidence"] == pytest.approx(0.77)


async def test_fusion_failure_degrades_to_unimodal(monkeypatch):
    """A malformed counterpart must not drop the cycle — it must fall back, not fail."""
    monkeypatch.setattr("app.agents.nodes.affect_detection.predict_from_window",
                        lambda events, started: _behavioural_result(0.81))

    def boom(**kwargs):
        raise RuntimeError("bad counterpart")

    monkeypatch.setattr("app.agents.nodes.affect_detection.fuse_modalities", boom)
    state = make_initial_state(learner_id="u", session_id="s", cycle_number=4,
                               behavioral_payload={"events": [], "capture_started_at_wall": 0},
                               counterpart_inference=_facial_result(0.9),
                               counterpart_modality="facial")
    out = await affect_detection_node(state)
    assert out["affect_state"] == "confused"
    assert out["affect_confidence"] == pytest.approx(0.81)
    assert out.get("fusion_applied") is not True


# --- the buffer contract that makes both consumers work --------------------------------

def test_peek_does_not_consume_so_the_event_still_pairs():
    """The decision peeks; `_maybe_fuse` takes. If peek consumed, the log would go unpaired."""
    fusion_buffer.record("s", "facial", _facial_result(0.7), 1_000)
    first = fusion_buffer.peek_counterpart("s", "behavioral", 1_100)
    assert first is not None
    assert fusion_buffer.peek_counterpart("s", "behavioral", 1_100) is not None, \
        "peek consumed the slot"
    assert fusion_buffer.take_counterpart("s", "behavioral", 1_100) is not None
    assert fusion_buffer.peek_counterpart("s", "behavioral", 1_100) is None


def test_peek_respects_the_pairing_window():
    from app.agents.fusion import FUSION_PAIR_WINDOW_MS
    fusion_buffer.record("s", "facial", _facial_result(0.7), 1_000)
    stale = 1_000 + FUSION_PAIR_WINDOW_MS + 1
    assert fusion_buffer.peek_counterpart("s", "behavioral", stale) is None


def test_peek_returns_a_copy():
    """A mutation downstream must not corrupt the buffered result the event will read."""
    fusion_buffer.record("s", "facial", _facial_result(0.7), 1_000)
    got = fusion_buffer.peek_counterpart("s", "behavioral", 1_050)
    got["confidence"] = 0.0
    again = fusion_buffer.peek_counterpart("s", "behavioral", 1_050)
    assert again["confidence"] == pytest.approx(0.7)
