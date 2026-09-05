"""The geometry channel: mapping, provenance, and its authority at the adaptation gate.

Three things are asserted here that no existing test could cover, because before this artifact
none of them were true:

  * `bored` is reachable. Every other model pins it at 0.0 in the canonical vector, so
    `ADAPT_STATES` has listed an actionable state that nothing could produce.
  * A FACIAL channel may intervene. `DECISIVE_AFFECT_SOURCES` was introduced to stop exactly that,
    and the grant here rests on measured precision (0.872 vs 0.500 at the same 0.70 floor), so a
    test must pin which facial source is decisive and which is not.
  * Two disjoint channels must not be averaged. The behavioural channel votes on `confused` and
    zeroes `bored`; this one does the reverse. Weighted-averaging halves both, which is the
    documented zero-intervention failure.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.agents.affect_mapping import (
    BINARY_DISENGAGED_INDEX,
    binary_disengagement_to_affect,
    resolve_affect,
)
from app.agents.edges import (
    ADAPT_MIN_CONFIDENCE,
    GATE_CHANNEL_ADVISORY,
    GATE_OK,
    is_decisive,
    passes_adaptation_gate,
)
from app.agents.fusion import CANONICAL_ORDER, facial_to_canonical
from app.agents.state import (
    AFFECT_SOURCE_BEHAVIORAL,
    AFFECT_SOURCE_CATEGORY,
    AFFECT_SOURCE_ENGAGEMENT,
    AFFECT_SOURCE_FACIAL_GEOMETRY,
)


# ── mapping ───────────────────────────────────────────────────────────────────────────

def test_positive_class_maps_to_bored():
    """1 -> bored. This is a DETECTION of an actionable state, not an inference from absence."""
    assert binary_disengagement_to_affect(BINARY_DISENGAGED_INDEX) == "bored"


def test_negative_class_maps_to_engaged_not_bored():
    """0 means 'no disengagement detected', which must not route into an actionable state."""
    assert binary_disengagement_to_affect(0) == "engaged"


def test_resolve_affect_tags_its_own_provenance():
    """Must NOT reuse AFFECT_SOURCE_CATEGORY: that marker is non-decisive and this channel is."""
    state, source, conf, extra = resolve_affect(
        {"engagement_level": 1, "confidence": 0.91, "probs": [0.09, 0.91]}, kind="geometry"
    )
    assert (state, source) == ("bored", AFFECT_SOURCE_FACIAL_GEOMETRY)
    assert conf == pytest.approx(0.91)
    assert extra["p_disengaged"] == pytest.approx(0.91)


def test_resolve_affect_records_raw_probability_even_when_negative():
    """P(disengaged) is logged every cycle so the gate can be recalibrated from logs later."""
    _, _, _, extra = resolve_affect(
        {"engagement_level": 0, "confidence": 0.88, "probs": [0.88, 0.12]}, kind="geometry"
    )
    assert extra["p_disengaged"] == pytest.approx(0.12)


# ── authority at the gate ─────────────────────────────────────────────────────────────

def test_geometry_channel_is_decisive():
    assert is_decisive(AFFECT_SOURCE_FACIAL_GEOMETRY) is True


@pytest.mark.parametrize("source", [AFFECT_SOURCE_CATEGORY, AFFECT_SOURCE_ENGAGEMENT])
def test_the_older_facial_channels_stay_advisory(source):
    """Granting authority to the geometric model must not grant it to the DAiSEE-trained one."""
    assert is_decisive(source) is False


def test_bored_can_now_pass_the_gate():
    """The state ADAPT_STATES has always listed but nothing could produce."""
    ok, reason = passes_adaptation_gate(
        affect_state="bored",
        affect_confidence=0.90,
        affect_history=["bored", "bored"],
        affect_source=AFFECT_SOURCE_FACIAL_GEOMETRY,
        cycle_number=10,
        last_adaptation_cycle=None,
    )
    assert (ok, reason) == (True, GATE_OK)


def test_same_reading_from_the_old_facial_channel_is_blocked():
    """Identical confidence and history — only provenance differs, and it must decide the outcome."""
    ok, reason = passes_adaptation_gate(
        affect_state="bored",
        affect_confidence=0.90,
        affect_history=["bored", "bored"],
        affect_source=AFFECT_SOURCE_ENGAGEMENT,
        cycle_number=10,
        last_adaptation_cycle=None,
    )
    assert (ok, reason) == (False, GATE_CHANNEL_ADVISORY)


def test_confidence_floor_still_applies_to_this_channel():
    """Decisive authority is not an exemption from the floor."""
    ok, _ = passes_adaptation_gate(
        affect_state="bored",
        affect_confidence=ADAPT_MIN_CONFIDENCE - 0.01,
        affect_history=["bored", "bored"],
        affect_source=AFFECT_SOURCE_FACIAL_GEOMETRY,
        cycle_number=10,
        last_adaptation_cycle=None,
    )
    assert ok is False


# ── projection, and why these channels are not fused ──────────────────────────────────

def test_projection_votes_on_bored_and_abstains_elsewhere():
    """A channel that cannot see a state must not vote on it."""
    v = facial_to_canonical({"probs": [0.2, 0.8]}, kind="geometry")
    assert dict(zip(CANONICAL_ORDER, v)) == pytest.approx(
        {"bored": 0.8, "confused": 0.0, "engaged": 0.2, "frustrated": 0.0}
    )


def test_averaging_disjoint_channels_would_halve_a_real_detection():
    """The reason FUSION_DRIVES_DECISION is off wherever this artifact is deployed.

    Behavioural says confused at 0.90; geometry says bored at 0.90. Both are confident, correct
    and about DIFFERENT states. An equal-weighted mean puts each at 0.45 — under the 0.70 floor —
    so a cycle in which two channels each detected something clearly would intervene on nothing.
    """
    geometry = facial_to_canonical({"probs": [0.10, 0.90]}, kind="geometry")
    behavioural = np.array([0.0, 0.90, 0.10, 0.0])          # bored, confused, engaged, frustrated

    fused = (geometry + behavioural) / 2.0
    assert fused.max() == pytest.approx(0.45)
    assert fused.max() < ADAPT_MIN_CONFIDENCE

    # Routed per channel instead, each detection clears the floor on its own.
    assert geometry.max() >= ADAPT_MIN_CONFIDENCE
    assert behavioural.max() >= ADAPT_MIN_CONFIDENCE


# ── node dispatch ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_node_routes_geometry_payloads_to_the_geometry_model(monkeypatch):
    """Dispatch is on the PAYLOAD's shape, not an env flag.

    A client that has not been updated still sends frames_b64, and both must keep working
    during a rollout — reading the payload is the only way to know which arrived.
    """
    from app.agents.nodes import affect_detection as node

    seen: dict = {}

    def fake_geometry(payload):
        seen["geometry"] = payload
        return {"engagement_level": 1, "label": "disengaged",
                "confidence": 0.93, "probs": [0.07, 0.93]}

    def fake_pixels(*args, **kwargs):
        seen["pixels"] = True
        return {"engagement_level": 0}

    monkeypatch.setattr(node, "predict_geometry", fake_geometry)
    monkeypatch.setattr(node, "predict_from_payload", fake_pixels)

    out = await node.detect_engagement({
        "cycle_number": 3,
        "frames_captured": 10,
        "face_absent": False,
        "geometry": [[0.0] * 11 for _ in range(10)],
    })
    assert out is not None and out["label"] == "disengaged"
    assert "geometry" in seen and "pixels" not in seen


@pytest.mark.asyncio
async def test_node_still_serves_the_pixel_client(monkeypatch):
    from app.agents.nodes import affect_detection as node

    seen: dict = {}
    monkeypatch.setattr(node, "predict_geometry",
                        lambda p: seen.setdefault("geometry", True))
    monkeypatch.setattr(node, "predict_from_payload",
                        lambda b, n: seen.setdefault("pixels", True) or {"engagement_level": 0})

    await node.detect_engagement({
        "cycle_number": 3, "frames_captured": 16,
        "face_absent": False, "frames_b64": "AAAA",
    })
    assert "pixels" in seen and "geometry" not in seen


@pytest.mark.asyncio
async def test_empty_chair_is_blocked_before_either_branch(monkeypatch):
    """An absent learner must produce no reading whichever channel carries the payload."""
    from app.agents.nodes import affect_detection as node
    monkeypatch.setattr(node, "predict_geometry",
                        lambda p: pytest.fail("inference ran for an absent learner"))

    out = await node.detect_engagement({
        "cycle_number": 4, "frames_captured": 10, "face_absent": True,
        "geometry": [[0.0] * 11 for _ in range(10)],
    })
    assert out is None


# ── per-channel confidence floors ─────────────────────────────────────────────────────

def test_each_channel_gets_its_own_calibrated_floor():
    """A single global floor would force one channel onto the other's operating point.

    The two were calibrated separately and their probability distributions are not comparable:
    geometry reaches 0.872 precision at 0.70, while behavioural was tuned to 0.50 in production.
    """
    from app.agents.edges import ADAPT_MIN_CONFIDENCE, min_confidence_for

    assert min_confidence_for(AFFECT_SOURCE_FACIAL_GEOMETRY) == 0.70
    # Anything without an override keeps the global setting, so nothing else moves.
    assert min_confidence_for(AFFECT_SOURCE_BEHAVIORAL) == ADAPT_MIN_CONFIDENCE
    assert min_confidence_for(None) == ADAPT_MIN_CONFIDENCE


def test_geometry_below_its_own_floor_is_blocked_even_if_above_the_global_one(monkeypatch):
    """0.60 clears a 0.50 global floor but not geometry's 0.70. The channel floor must win."""
    import app.agents.edges as edges
    monkeypatch.setattr(edges, "ADAPT_MIN_CONFIDENCE", 0.50)

    ok, reason = edges.passes_adaptation_gate(
        affect_state="bored",
        affect_confidence=0.60,
        affect_history=["bored", "bored"],
        affect_source=AFFECT_SOURCE_FACIAL_GEOMETRY,
        cycle_number=10,
        last_adaptation_cycle=None,
    )
    assert (ok, reason) == (False, edges.GATE_LOW_CONFIDENCE)

    # The same confidence from the behavioural channel passes, because 0.50 is its floor.
    ok2, reason2 = edges.passes_adaptation_gate(
        affect_state="confused",
        affect_confidence=0.60,
        affect_history=["confused", "confused"],
        affect_source=AFFECT_SOURCE_BEHAVIORAL,
        cycle_number=10,
        last_adaptation_cycle=None,
    )
    assert (ok2, reason2) == (True, edges.GATE_OK)
