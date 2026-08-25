"""An absent learner must not produce an affect reading.

Regression context: faceless frames used to be DROPPED browser-side, so an empty chair yielded
`frames_captured == 0` and `detect_engagement` returned None -> empty cycle -> behavioural-only.
When the capture path started emitting a CENTRE CROP for faceless frames (needed to match the
training distribution), that safety property silently disappeared: an empty chair produced a full
16-frame clip and the model returned a confident-looking reading for nobody, which the adaptation
gate could act on.

The browser now reports `face_absent` and it is honoured at the same boundary.
"""

from __future__ import annotations

import pytest

from app.agents.nodes.affect_detection import detect_engagement

# Any non-empty string passes the frames_b64 guard; inference must be rejected BEFORE decoding,
# so these payloads never need to be valid tensors.
_B64 = "AAAA"


async def test_face_absent_returns_none_even_with_frames():
    """The regression itself: frames present, no face -> no inference."""
    out = await detect_engagement({
        "frames_b64": _B64,
        "frames_captured": 30,
        "frames_with_face": 2,
        "face_ratio": 0.067,
        "face_absent": True,
        "cycle_number": 7,
    })
    assert out is None


async def test_zero_frames_still_returns_none():
    """The original guard must keep working."""
    assert await detect_engagement({"frames_b64": "", "frames_captured": 0}) is None
    assert await detect_engagement({"frames_b64": _B64, "frames_captured": 0}) is None


async def test_missing_face_absent_key_does_not_suppress(monkeypatch):
    """Older clients omit the field entirely; absence of the flag is not absence of a face."""
    called = {}

    def fake(frames_b64, frames_captured):
        called["yes"] = (frames_b64, frames_captured)
        return {"engagement_level": 1, "label": "confused", "confidence": 0.6, "probs": [0.4, 0.6]}

    monkeypatch.setattr("app.agents.nodes.affect_detection.predict_from_payload", fake)
    out = await detect_engagement({"frames_b64": _B64, "frames_captured": 16})
    assert out is not None
    assert called["yes"] == (_B64, 16)


async def test_face_present_runs_inference(monkeypatch):
    def fake(frames_b64, frames_captured):
        return {"engagement_level": 1, "label": "confused", "confidence": 0.6, "probs": [0.4, 0.6]}

    monkeypatch.setattr("app.agents.nodes.affect_detection.predict_from_payload", fake)
    out = await detect_engagement({
        "frames_b64": _B64,
        "frames_captured": 30,
        "frames_with_face": 28,
        "face_ratio": 0.933,
        "face_absent": False,
    })
    assert out is not None
    assert out["label"] == "confused"


@pytest.mark.parametrize("flag", [True, 1, "true"])
async def test_any_truthy_face_absent_suppresses(flag):
    """Wire values arrive from JSON; do not depend on a strict bool."""
    out = await detect_engagement({
        "frames_b64": _B64, "frames_captured": 30, "face_absent": flag,
    })
    assert out is None


async def test_suppression_happens_before_decoding(monkeypatch):
    """Cheap rejection: an absent cycle must never reach the model."""
    def boom(*a, **k):  # pragma: no cover - must not run
        raise AssertionError("inference ran for a face-absent cycle")

    monkeypatch.setattr("app.agents.nodes.affect_detection.predict_from_payload", boom)
    assert await detect_engagement({
        "frames_b64": _B64, "frames_captured": 30, "face_absent": True,
    }) is None
