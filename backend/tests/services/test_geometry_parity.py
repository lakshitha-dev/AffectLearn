"""Train/serve parity for the facial-geometry channel.

WHY THIS TEST EXISTS

The geometry model consumes 20 numbers that are computed in two different languages: Python at
training time (`training/engagenet/extract_geometry.py` + `rungs.py`) and TypeScript at serve time
(`frontend/src/lib/geometry.ts`), aggregated by `app/services/geometry_inference.py`. Nothing about
a mismatch is loud — the model keeps returning confident probabilities from features it was never
trained on.

This project has already paid for exactly that. The pixel path trained on frames spaced 1.93 s
apart while serving frames spaced 0.67 s apart, and no test compared the two, so the divergence
was found only by reading the code months later.

`geometry_golden.npz` freezes 20 real windows and the feature vectors the training pipeline
produced from them. It contains derived measurements only — no EngageNet video, no labels, and no
clip identifiers — so it is committable under the corpus licence.

The fixture deliberately includes windows with undetected faces (74 NaN readings across the 20
windows), because that is where a careless port diverges first: `mean` and `nanmean` agree on
clean data and disagree exactly when a learner looks away, which is the event being detected.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.services.geometry_inference import (
    EXPECTED_FRAMES,
    FEATURE_NAMES,
    GEOMETRY_CHANNEL_ORDER,
    MODEL_CHANNELS,
    N_FEATURES,
    build_features,
    five_stats,
)

GOLDEN = Path(__file__).parent.parent / "fixtures" / "geometry_golden.npz"


@pytest.fixture(scope="module")
def golden():
    if not GOLDEN.exists():
        pytest.skip(f"golden fixture missing: {GOLDEN}")
    return np.load(GOLDEN, allow_pickle=False)


def test_channel_order_matches_training(golden):
    """The serve-side channel order must equal the one the extractor emitted."""
    assert list(golden["channel_order"]) == list(GEOMETRY_CHANNEL_ORDER)


def test_feature_names_and_order_match_training(golden):
    """Feature ORDER is the contract, not just the set — the model indexes by position."""
    assert list(golden["feature_names"]) == list(FEATURE_NAMES)
    assert len(FEATURE_NAMES) == N_FEATURES == 20


def test_build_features_reproduces_training_vectors(golden):
    """The whole point: serve-side aggregation must reproduce training-side aggregation.

    Tolerance is float32 storage precision, not a fudge factor — the fixture stores geometry as
    float32 while training computed in float64.
    """
    geometry, expected = golden["geometry"], golden["features"]
    for i in range(geometry.shape[0]):
        got = build_features(geometry[i].tolist())
        assert got.shape == (1, N_FEATURES)
        np.testing.assert_allclose(
            got[0], expected[i], rtol=1e-5, atol=1e-5,
            err_msg=f"window {i} diverged from the training pipeline",
        )


def test_nan_frames_are_handled_as_missing_not_zero(golden):
    """A frame with no detected face must be ABSENT from the statistics, not counted as zero.

    Zero is a meaningful reading for gaze — it means looking straight ahead. Treating an undetected
    face as zero would record "attentive" precisely when the learner has looked away, inverting the
    signal the model exists to detect.
    """
    geometry = golden["geometry"]
    has_nan = [i for i in range(geometry.shape[0]) if np.isnan(geometry[i]).any()]
    assert has_nan, "fixture no longer covers the missing-face case; regenerate it"

    seq = geometry[has_nan[0]][:, [GEOMETRY_CHANNEL_ORDER.index(c) for c in MODEL_CHANNELS]]
    nan_aware = five_stats(seq.astype(np.float64))
    naive = np.concatenate([seq.mean(axis=0), seq.std(axis=0),
                            seq.min(axis=0), seq.max(axis=0),
                            seq[-3:].mean(axis=0) - seq[:3].mean(axis=0)]).astype(np.float64)
    assert not np.allclose(np.nan_to_num(nan_aware), np.nan_to_num(naive)), (
        "nan-aware and naive aggregation agree, so this fixture cannot detect the bug it guards"
    )
    assert np.isfinite(nan_aware).all() or np.isnan(nan_aware).any()


def test_frame_spacing_is_pinned():
    """10 frames at 1 fps. The constant that drifted unnoticed on the pixel path."""
    assert EXPECTED_FRAMES == 10


def test_wrong_channel_count_raises_rather_than_pads(golden):
    """A short row means the browser and the server disagree; padding would hide that."""
    short = golden["geometry"][0][:, :5].tolist()
    with pytest.raises(ValueError, match="expected"):
        build_features(short)


def test_output_is_finite_and_float32(golden):
    """ONNX rejects NaN; an all-missing channel must still produce a scoreable vector."""
    x = build_features(golden["geometry"][0].tolist())
    assert x.dtype == np.float32
    assert np.isfinite(x).all()


def test_empty_window_does_not_crash():
    """Zero rows is a contract violation, not a crash site."""
    with pytest.raises(ValueError):
        build_features([])


# ── research export: the two binary channels must not share a column ──────────────────

def test_export_files_each_channel_probability_under_its_own_heading():
    """probs[1] means P(confused) for one facial artifact and P(disengaged) for the other.

    The export's old fallback read probs[1] unconditionally, so geometry rows were written into a
    column headed `p_confused`. Nothing downstream could detect that: the value is a plausible
    probability in a plausible column, and an analysis would simply be wrong.
    """
    from app.services.monitor_export_service import COLUMNS, _row

    class Ev:
        timestamp = 1788617827594
        session_id = "s"; learner_id = "l"; cycle_number = 1; sequence_number = 3
        event_type = "facial_affect_detected"; phase = "phase_b"; group = "control"
        def __init__(self, payload): self.payload = payload

    cols = list(COLUMNS)
    ic, idg = cols.index("p_confused"), cols.index("p_disengaged")

    # Geometry row carrying only a softmax, as the live rows did.
    row = _row(Ev({"affect_state": "bored", "probs": [0.055, 0.945], "affect_source": "facial_geometry"}))
    assert row[idg] == 0.945
    assert row[ic] == "", "P(disengaged) must not be filed as P(confused)"

    # The confusion artifact keeps the original behaviour.
    row = _row(Ev({"affect_state": "confused", "probs": [0.2, 0.8], "affect_source": "category_model"}))
    assert row[ic] == 0.8
    assert row[idg] == ""

    # A row with no provenance at all: `bored` is producible only by the geometry channel.
    row = _row(Ev({"affect_state": "bored", "probs": [0.1, 0.9]}))
    assert row[idg] == 0.9 and row[ic] == ""


def test_export_prefers_the_explicit_field_over_the_softmax_fallback():
    from app.services.monitor_export_service import COLUMNS, _row

    class Ev:
        timestamp = 1; session_id = "s"; learner_id = "l"
        cycle_number = 1; sequence_number = 1
        event_type = "facial_affect_detected"; phase = "phase_b"; group = "adaptive"
        def __init__(self, payload): self.payload = payload

    cols = list(COLUMNS)
    row = _row(Ev({"affect_state": "bored", "p_disengaged": 0.87, "probs": [0.4, 0.6]}))
    assert row[cols.index("p_disengaged")] == 0.87
