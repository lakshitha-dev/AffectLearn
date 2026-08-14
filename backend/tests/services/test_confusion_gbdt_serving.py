"""The aggregate/GBDT serving path, exercised against the REAL exported ONNX.

These run on `models/behavioral_confusion_gbdt.onnx` rather than a stub, because the failure modes
that matter here are all about the boundary between the extractor and the artifact: feature width,
feature ORDER, whether normalisation is applied, and which output tensor holds the probabilities.
A mock would agree with whatever the code does and catch none of them.

The path replaces a Bi-LSTM exported from a checkpoint stamped `trained_on: "synthetic"` (600
fabricated windows, 15 fabricated participants) with a GBDT trained on 1,419 windows from 46 real
participants, AUC 0.747 leave-one-participant-out. Given that history, "the model loads and returns
a number" is not a sufficient test.
"""

import numpy as np
import pytest

from app.services.behavioral_inference import (
    BEHAVIORAL_CLASS_ORDER,
    BehavioralModel,
)
from app.services.feature_engineering import N_FEATURES

GBDT = "models/behavioral_confusion_gbdt.onnx"
pytestmark = pytest.mark.skipif(
    not __import__("os").path.exists(GBDT),
    reason=f"{GBDT} not present (gitignored in the ML repo; tracked here)",
)


@pytest.fixture(scope="module")
def model() -> BehavioralModel:
    return BehavioralModel(model_path=GBDT)


def test_kind_detected_from_the_onnx_signature(model):
    """Auto-detection is what keeps artifact and code path from disagreeing.

    A 2-D input means aggregate features; 3-D means a sequence. Nothing reads an env var, so
    there is no flag to set wrongly.
    """
    assert model._kind() == "aggregate"
    assert model.session.get_inputs()[0].shape[-1] == 80


def test_idle_window_is_not_called_confused(model):
    """An all-zero window is a real low-activity input, and must read as calm.

    If this ever flips it means the feature ORDER changed between the extractor and the exported
    model — the trees would then be splitting on the wrong columns, which produces confident
    nonsense rather than an error.
    """
    r = model.infer(np.zeros((30, N_FEATURES), dtype=np.float32))
    assert r["label"] == "engaged"
    assert r["p_confused"] < 0.25, f"idle window scored p_confused={r['p_confused']:.3f}"


def test_probabilities_are_a_valid_distribution(model):
    rng = np.random.default_rng(0)
    for _ in range(8):
        r = model.infer((rng.random((30, N_FEATURES)) * 2).astype(np.float32))
        assert len(r["probs"]) == len(BEHAVIORAL_CLASS_ORDER)
        assert sum(r["probs"]) == pytest.approx(1.0)
        assert all(0.0 <= p <= 1.0 for p in r["probs"])
        assert r["probs"][r["affect_index"]] == pytest.approx(r["confidence"])


def test_unseeable_states_are_pinned_at_zero(model):
    """This model detects confusion and nothing else.

    Emitting any mass on bored or frustrated would let the adaptation gate fire an intervention
    for a state with no evidence behind it — both are in ADAPT_STATES by default.
    """
    rng = np.random.default_rng(1)
    for _ in range(8):
        r = model.infer((rng.random((30, N_FEATURES)) * 3).astype(np.float32))
        assert r["probs"][BEHAVIORAL_CLASS_ORDER.index("bored")] == 0.0
        assert r["probs"][BEHAVIORAL_CLASS_ORDER.index("frustrated")] == 0.0


def test_engaged_carries_the_complement_of_confused(model):
    rng = np.random.default_rng(2)
    r = model.infer((rng.random((30, N_FEATURES)) * 2).astype(np.float32))
    i_eng = BEHAVIORAL_CLASS_ORDER.index("engaged")
    i_conf = BEHAVIORAL_CLASS_ORDER.index("confused")
    assert r["probs"][i_eng] == pytest.approx(1.0 - r["probs"][i_conf])
    assert r["probs"][i_conf] == pytest.approx(r["p_confused"])


def test_model_kind_is_reported_for_provenance(model):
    """Research events must record WHICH model produced a label, given the synthetic history."""
    r = model.infer(np.zeros((30, N_FEATURES), dtype=np.float32))
    assert r["model_kind"] == "aggregate_confusion_gbdt"


def test_normalisation_is_NOT_applied_on_this_path(model, monkeypatch):
    """The trees were fitted on RAW aggregates; z-scoring them would silently shift every input.

    Poisoning the z-score stats must therefore change nothing. If this test starts failing,
    someone has "helpfully" routed the aggregate path through `_normalize`.
    """
    feats = np.zeros((30, N_FEATURES), dtype=np.float32)
    before = model.infer(feats)["p_confused"]
    monkeypatch.setattr(
        model, "_stats",
        {"mean": np.full(N_FEATURES, 999.0, dtype=np.float32),
         "std": np.full(N_FEATURES, 0.001, dtype=np.float32)},
    )
    assert model.infer(feats)["p_confused"] == pytest.approx(before)


def test_varying_input_varies_the_output(model):
    """Guards against a degenerate export that returns a constant regardless of input."""
    rng = np.random.default_rng(3)
    ps = {model.infer((rng.random((30, N_FEATURES)) * 4).astype(np.float32))["p_confused"]
          for _ in range(12)}
    assert len(ps) > 1, "the model returned an identical probability for every input"


def test_sequence_path_still_detected_for_the_bilstm():
    """Regression guard: the historic Bi-LSTM artifact must not be routed to the GBDT path."""
    import os
    bilstm = "models/behavioral_bilstm.onnx"
    if not os.path.exists(bilstm):
        pytest.skip("bilstm artifact not present")
    assert BehavioralModel(model_path=bilstm)._kind() == "sequence"
