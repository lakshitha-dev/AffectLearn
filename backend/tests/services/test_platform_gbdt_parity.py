"""Train/serve parity for the platform-matched confusion model, end to end from the WIRE format.

`behavioral_confusion_gbdt_platform.onnx` is the deployed GBDT refitted on DUX rebuilt to look like
what the browser sends (one pointer sample per 100 ms, one click per press, windows scored from one
event; affectlearn-ml `training/behavioral/export_dux_confusion_platform.py`).

The fixture holds 14 of its training windows converted to `behavioral_window` events, with the
P(confused) the ML pipeline computed for each. Replaying them through `predict_from_window` covers
every step a feature-level test skips: the event adapter, the viewport normalisation, the key
categories, the scroll deltas, the extractor, the aggregation and the ONNX call.

Parity is all this proves. The model was trained on people filling in forms, and nothing here says
it detects confusion on lesson pages.
"""

import json
import os
from pathlib import Path

import numpy as np
import pytest

from app.services.behavioral_inference import BehavioralModel, predict_from_window
from app.services.feature_engineering import N_FEATURES

MODEL = "models/behavioral_confusion_gbdt_platform.onnx"
FIXTURE = Path(__file__).parents[1] / "fixtures" / "behavioral_platform_parity.json"
pytestmark = pytest.mark.skipif(not os.path.exists(MODEL), reason=f"{MODEL} not present")


@pytest.fixture(scope="module")
def model() -> BehavioralModel:
    return BehavioralModel(model_path=MODEL)


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_it_serves_through_the_aggregate_path(model):
    assert model._kind() == "aggregate"
    assert model.session.get_inputs()[0].shape[-1] == 80


def test_the_backend_reproduces_the_training_pipeline(model, fixture):
    for i, window in enumerate(fixture["windows"]):
        served = predict_from_window(window["events"], fixture["capture_started_at_wall"], model)
        assert served["p_confused"] == pytest.approx(window["p_confused"], abs=1e-4), i


def test_an_idle_window_reads_as_calm(model):
    assert model.infer(np.zeros((30, N_FEATURES), dtype=np.float32))["p_confused"] < 0.25


def test_its_scores_reach_the_floor_on_platform_input(model, fixture):
    """What the retrain is for: on platform-shaped input the deployed model's scores shrink
    below its 0.70 floor; this one's reach it."""
    served = [predict_from_window(w["events"], fixture["capture_started_at_wall"], model)
              ["p_confused"] for w in fixture["windows"]]
    assert max(served) >= 0.70
