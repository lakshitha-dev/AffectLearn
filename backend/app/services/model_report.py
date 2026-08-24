"""Which affect models are ACTUALLY loaded, and how the code will interpret them.

Shared by `GET /health/pipeline` (unauthenticated liveness) and `GET /api/v1/monitor/health`
(admin dashboard) so the two can never disagree. Previously `monitor.py` kept its OWN
module-level `BEHAVIORAL_MODEL_PATH` / `AFFECT_MODEL_PATH` constants read at import time with
defaults that had been superseded (`behavioral_bilstm.onnx`, `cnn_lstm_best.onnx`), so the
admin dashboard reported the old artifacts while the pipeline served the new ones.

That is the same staleness class that made the model swap invisible during deploy: env read
once at import, never revisited. Resolving paths per call, in one place, is the fix.

Deploy verification exists because the failure modes here are silent. Pointing
AFFECT_MODEL_KIND at `binary_confusion` while AFFECT_MODEL_PATH still resolves to the
4-level engagement artifact produces confident nonsense, not an error.

Never raises -- every probe is guarded so a broken artifact reports rather than 500s.
No secrets: paths and shapes only.
"""

from __future__ import annotations

import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _onnx_io(path: str) -> dict[str, Any]:
    """Input/output names and shapes, so a width mismatch is visible before inference."""
    try:
        import onnxruntime as ort

        sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        return {
            "inputs": [{"name": i.name, "shape": i.shape} for i in sess.get_inputs()],
            "outputs": [{"name": o.name, "shape": o.shape} for o in sess.get_outputs()],
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def behavioral_report() -> dict[str, Any]:
    """Resolved behavioural artifact: path, presence, adapter kind, ONNX IO."""
    try:
        from app.services.behavioral_inference import _DEFAULT_MODEL_PATH, BehavioralModel

        path = os.getenv("BEHAVIORAL_MODEL_PATH", _DEFAULT_MODEL_PATH)
        rep: dict[str, Any] = {"path": path, "exists": os.path.exists(path)}
        if rep["exists"]:
            try:
                rep["kind"] = BehavioralModel(model_path=path)._kind()
            except Exception as exc:
                rep["kind"] = f"unresolved: {type(exc).__name__}"
            rep.update(_onnx_io(path))
        return rep
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def facial_report() -> dict[str, Any]:
    """Resolved facial artifact: path, presence, adapter kind, ONNX IO."""
    try:
        from app.agents.affect_mapping import _model_kind

        path = os.getenv("AFFECT_MODEL_PATH", "models/cnn_lstm_best.onnx")
        rep: dict[str, Any] = {
            "path": path,
            "exists": os.path.exists(path),
            "kind": _model_kind(),
        }
        if rep["exists"]:
            rep.update(_onnx_io(path))
        return rep
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def decision_report() -> dict[str, Any]:
    """The gate/fusion configuration that turns a detection into an intervention."""
    try:
        from app.agents.edges import (
            ADAPT_COOLDOWN_CYCLES,
            ADAPT_MIN_CONFIDENCE,
            ADAPT_MIN_CONSECUTIVE,
            ADAPT_STATES,
        )
        from app.agents.fusion import forced_mode
        from app.agents.nodes.affect_detection import fusion_drives_decision

        return {
            "adaptStates": list(ADAPT_STATES),
            "adaptMinConfidence": ADAPT_MIN_CONFIDENCE,
            "adaptMinConsecutive": ADAPT_MIN_CONSECUTIVE,
            "adaptCooldownCycles": ADAPT_COOLDOWN_CYCLES,
            "fusionDrivesDecision": fusion_drives_decision(),
            "forcedMode": forced_mode(),
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def model_report() -> dict[str, Any]:
    """Full report: both artifacts plus the decision-path config.

    Deliberately NOT part of any `status` verdict: a missing facial ONNX is a documented
    degradation (the pipeline runs behavioural-only, see models/README.md), not an outage.
    """
    return {
        "behavioral": behavioral_report(),
        "facial": facial_report(),
        "decision": decision_report(),
    }
