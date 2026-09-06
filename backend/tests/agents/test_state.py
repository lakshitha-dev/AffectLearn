"""Unit tests for AgentState constants and seeding (Story 4.4)."""

from app.agents.state import (
    AFFECT_STATES,
    DETECTION_MODES,
    GROUPS,
    PHASES,
    make_initial_state,
)


def test_locked_value_sets_match_architecture():
    assert AFFECT_STATES == ("bored", "confused", "engaged", "frustrated")
    assert PHASES == ("phase_a", "phase_b")
    assert GROUPS == ("adaptive", "control")


def test_detection_modes_include_the_performance_channel():
    """EXTENDED deliberately, and the addition is not a sensing modality.

    `performance_only` means no model ran: the reading came from what the learner DID -- wrong
    answers, revealing an answer, going back to re-read. It is listed as a detection mode so a
    research event can be filtered to the channel that produced it, and so an analysis can
    separate model-driven interventions from behaviour-driven ones without having to infer which
    was which after the fact.

    The three original modes keep their positions: anything persisted against them stays valid.
    """
    assert DETECTION_MODES == (
        "multimodal", "facial_only", "behavioral_only", "performance_only",
    )
    assert DETECTION_MODES[:3] == ("multimodal", "facial_only", "behavioral_only")


def test_make_initial_state_defaults_to_phase_a_control():
    state = make_initial_state(learner_id="u1", session_id="s1", cycle_number=3)
    assert state["learner_id"] == "u1"
    assert state["session_id"] == "s1"
    assert state["cycle_number"] == 3
    assert state["phase"] == "phase_a"
    assert state["group"] == "control"
    assert state["facial_payload"] == {}
    # progressive fields are absent until nodes write them
    assert "affect_state" not in state


def test_make_initial_state_carries_facial_payload_and_overrides():
    payload = {"frames_b64": "AAAA", "frames_captured": 30}
    state = make_initial_state(
        learner_id="u1", session_id="s1", cycle_number=1,
        facial_payload=payload, phase="phase_b", group="adaptive",
    )
    assert state["facial_payload"] is payload
    assert state["phase"] == "phase_b"
    assert state["group"] == "adaptive"
