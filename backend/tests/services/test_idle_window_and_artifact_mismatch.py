"""Two silent-failure guards, both found in production telemetry.

1. An all-zeros behavioural window was classified as `engaged` with high confidence, so a
   learner who had walked away from the machine was recorded as engaged. The cause is in the
   training corpus rather than the model: DUX never populates `emotion_manual_Neutral`, so
   the negative class absorbed all calm AND all unannotated time, and an empty window
   therefore looks maximally not-confused.

2. `AFFECT_MODEL_KIND=binary_confusion` paired with the 4-level engagement artifact produced
   P(confused) sitting in a 0.067-wide band around 0.50 across 29 consecutive cycles -- a
   coin flip that reads as a working model making weak predictions. `model_report` printed
   the kind and the path but never compared them.
"""

import pytest

from app.services.behavioral_inference import _is_idle, predict_from_window
from app.services.model_report import _kind_artifact_mismatch

START = 1_700_000_000_000


def _mk(**kw):
    """One event with the wire schema the adapter expects (`kind`, `t_wall`)."""
    e = {"kind": "mouse_sample", "t_wall": START, "x": 100, "y": 100}
    e.update(kw)
    return e


class TestIdleDetection:
    def test_no_events_is_idle(self):
        assert predict_from_window([], START)["idle_window"] is True

    def test_visibility_only_is_idle(self):
        """Visibility events are dropped by the adapter, so they cannot make a window active."""
        events = [
            {"kind": "visibility", "t_wall": START + i * 3000, "state": "visible"}
            for i in range(10)
        ]
        assert predict_from_window(events, START)["idle_window"] is True

    @pytest.mark.parametrize(
        "event",
        [
            _mk(kind="mouse_sample"),
            _mk(kind="mouse_click"),
            _mk(kind="key", category="char"),
            _mk(kind="scroll", y=400),
        ],
        ids=["mouse", "click", "key", "scroll"],
    )
    def test_any_single_interaction_is_not_idle(self, event):
        """One real interaction of any kind is enough. Guards against over-suppression:
        a false positive here would silence every cycle."""
        assert predict_from_window([event], START)["idle_window"] is False

    def test_events_outside_the_window_are_idle(self):
        """Clamped away by the adapter, so they cannot make the window active."""
        far = [_mk(t_wall=START + 10_000_000)]
        assert predict_from_window(far, START)["idle_window"] is True

    def test_is_idle_fails_open_on_an_unexpected_type(self):
        """A suppression check must never silence a cycle because its input surprised it."""
        assert _is_idle(object()) is False

    def test_features_are_still_persisted_for_an_idle_window(self):
        """Suppression must not cost the research record -- Phase A needs the window."""
        r = predict_from_window([], START)
        assert r["features"], "idle windows still carry their feature array"
        assert len(r["features"]) == r["n_bins"]
        assert "feature_schema_version" in r


class TestKindArtifactMismatch:
    def test_binary_confusion_against_four_wide_artifact_is_flagged(self):
        """The exact production misconfiguration."""
        msg = _kind_artifact_mismatch(
            {"kind": "binary_confusion", "outputs": [{"shape": [None, 4]}]}
        )
        assert msg and "binary_confusion" in msg and "2" in msg and "4" in msg

    @pytest.mark.parametrize(
        "kind,width",
        [("binary_confusion", 2), ("engagement", 4), ("category", 4)],
    )
    def test_matching_pairs_are_silent(self, kind, width):
        assert _kind_artifact_mismatch({"kind": kind, "outputs": [{"shape": [None, width]}]}) is None

    @pytest.mark.parametrize(
        "rep",
        [
            {"kind": "binary_confusion"},                      # artifact absent
            {"outputs": [{"shape": [None, 4]}]},                # kind unresolved
            {"kind": "binary_confusion", "outputs": []},        # no outputs probed
            {"kind": "future_kind", "outputs": [{"shape": [None, 3]}]},   # unknown kind
            {"kind": "binary_confusion", "outputs": [{"shape": ["N", "d"]}]},  # symbolic dims
        ],
        ids=["no-outputs", "no-kind", "empty-outputs", "unknown-kind", "symbolic-shape"],
    )
    def test_never_raises_and_stays_quiet_when_it_cannot_tell(self, rep):
        """A reporting probe must never be the thing that breaks a health endpoint."""
        assert _kind_artifact_mismatch(rep) is None
