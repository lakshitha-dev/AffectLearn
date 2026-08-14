"""The `models` block on /health/pipeline — the deploy verification tool.

Why this exists: the dangerous failure mode when swapping affect models is SILENT. Setting
AFFECT_MODEL_KIND=binary_confusion while AFFECT_MODEL_PATH still resolves to the 4-level engagement
artifact produces confident nonsense, not an error, and the only previous way to notice was reading
App Service logs after a learner had already been affected. These tests pin the two properties that
make the endpoint trustworthy for that job: it reports the RESOLVED kind beside the file actually on
disk, and it never throws — a broken or absent artifact must degrade to a report, not a 500.
"""

import os

import pytest

from app.main import _model_report


def test_reports_the_behavioural_artifact_and_its_resolved_kind(monkeypatch):
    monkeypatch.setenv("BEHAVIORAL_MODEL_PATH", "models/behavioral_confusion_gbdt.onnx")
    r = _model_report()
    beh = r["behavioral"]
    assert beh["path"] == "models/behavioral_confusion_gbdt.onnx"
    if not beh["exists"]:
        pytest.skip("GBDT artifact not present in this checkout")
    # 'aggregate' is what routes inference through aggregate()+GBDT rather than the Bi-LSTM.
    assert beh["kind"] == "aggregate"
    assert beh["inputs"][0]["shape"][-1] == 80, "aggregate feature width must be visible"


def test_absent_model_reports_rather_than_raising(monkeypatch):
    """A missing facial ONNX is a documented degradation, not an outage."""
    monkeypatch.setenv("AFFECT_MODEL_PATH", "models/definitely-not-here.onnx")
    r = _model_report()
    assert r["facial"]["exists"] is False
    assert "error" not in r["facial"], "absence is not an error — it is a documented state"
    # No shapes probed for a file that is not there.
    assert "inputs" not in r["facial"]


def test_a_corrupt_artifact_reports_an_error_instead_of_500(monkeypatch, tmp_path):
    """A truncated blob download must surface here, not at the learner's first cycle."""
    bad = tmp_path / "truncated.onnx"
    bad.write_bytes(b"not an onnx graph")
    monkeypatch.setenv("AFFECT_MODEL_PATH", str(bad))
    r = _model_report()
    assert r["facial"]["exists"] is True
    assert "error" in r["facial"], "a corrupt graph must be reported, not silently accepted"


def test_kind_is_reported_even_when_the_file_is_missing(monkeypatch):
    """This is the mismatch detector: config saying one thing, disk saying another.

    Reporting `kind` independently of `exists` is what makes 'kind=binary_confusion' next to
    'exists=false' readable as "you set the env var but the blob never arrived".
    """
    monkeypatch.setenv("AFFECT_MODEL_KIND", "binary_confusion")
    monkeypatch.setenv("AFFECT_MODEL_PATH", "models/nope.onnx")
    r = _model_report()
    assert r["facial"]["kind"] == "binary_confusion"
    assert r["facial"]["exists"] is False


def test_decision_config_is_reported(monkeypatch):
    monkeypatch.setenv("ADAPT_STATES", "confused")
    monkeypatch.setenv("FUSION_DRIVES_DECISION", "1")
    d = _model_report()["decision"]
    assert d["fusionDrivesDecision"] is True
    assert d["adaptMinConfidence"] == pytest.approx(0.70)
    assert d["adaptMinConsecutive"] == 2
    assert "forcedMode" in d


def test_fusion_flag_off_is_visible(monkeypatch):
    """If someone reverts fusion in the portal, the endpoint must say so."""
    monkeypatch.setenv("FUSION_DRIVES_DECISION", "0")
    assert _model_report()["decision"]["fusionDrivesDecision"] is False


def test_no_secrets_leak_into_the_report():
    """The endpoint is documented as safe to poll — it must never echo credentials."""
    import json

    blob = json.dumps(_model_report()).lower()
    for forbidden in ("password", "secret", "token", "sas", "sig=", "postgresql://", "redis://"):
        assert forbidden not in blob, f"{forbidden!r} appeared in a pollable health payload"


async def test_endpoint_includes_models_and_status_ignores_them(client, monkeypatch):
    """`status` must stay a liveness verdict — a missing model must not page anyone."""
    monkeypatch.setenv("AFFECT_MODEL_PATH", "models/absent.onnx")
    resp = await client.get("/health/pipeline")
    assert resp.status_code == 200
    body = resp.json()
    assert "models" in body
    assert body["models"]["facial"]["exists"] is False
    # status is derived only from redis/postgres/worker
    assert body["status"] in ("ok", "degraded")
    expected = "ok" if (body["redis"] and body["postgres"] and body["worker"]["running"]) else "degraded"
    assert body["status"] == expected
