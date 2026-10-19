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


def _kind_artifact_mismatch(rep: dict[str, Any]) -> str | None:
    """Compare the configured adapter kind against the artifact's actual output width.

    This is the failure the module docstring warns about, and until now it was only
    *reported* -- both values were printed and a human had to notice they disagreed.
    A `binary_confusion` adapter reads two logits; the 4-level engagement export emits
    four. Pointing the kind at the wrong artifact yields confident nonsense with every
    probability sitting near 0.5, which looks like a working model producing weak
    predictions rather than like a misconfiguration.

    Returns a human-readable description, or None when kind and width agree.
    """
    kind = rep.get("kind")
    outputs = rep.get("outputs") or []
    if not kind or not outputs:
        return None

    width = None
    for o in outputs:
        shape = o.get("shape") or []
        if shape and isinstance(shape[-1], int):
            width = shape[-1]
            break
    if width is None:
        return None

    # "geometry" emits two probabilities over [engaged, disengaged]. Without an entry here the
    # guard returned None for it -- silently disabling the one check this module exists to make.
    expected = {"binary_confusion": 2, "geometry": 2, "engagement": 4, "category": 4}.get(kind)
    if expected is None or width == expected:
        return None
    return (
        f"AFFECT_MODEL_KIND={kind} expects {expected} output logits but the artifact at "
        f"its artifact emits {width}. Predictions from this pairing are meaningless."
    )


def facial_report() -> dict[str, Any]:
    """Resolved facial artifact: path, presence, adapter kind, ONNX IO."""
    try:
        from app.agents.affect_mapping import _model_kind

        kind = _model_kind()
        # Each facial kind loads its own artifact from its own env var. Reading AFFECT_MODEL_PATH
        # unconditionally described the RETIRED pixel model on a geometry deployment: the health
        # report named cnn_lstm_confusion_anycut.onnx, and where that file is absent it reported
        # exists=false, which drives the "Facial model not loaded" banner on the monitor and on
        # System Health while the geometry channel is running normally.
        if kind == "geometry":
            path = os.getenv("GEOMETRY_MODEL_PATH", "models/engagenet_lean_gbdt.onnx")
        else:
            path = os.getenv("AFFECT_MODEL_PATH", "models/cnn_lstm_confusion_anycut.onnx")
        rep: dict[str, Any] = {
            "path": path,
            "exists": os.path.exists(path),
            "kind": kind,
        }
        if rep["exists"]:
            rep.update(_onnx_io(path))
            rep["mismatch"] = _kind_artifact_mismatch(rep)
            if rep["mismatch"]:
                logger.error(
                    "facial_model_kind_artifact_mismatch",
                    kind=rep["kind"],
                    path=path,
                    detail=rep["mismatch"],
                )
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
        from app.agents import edges
        from app.agents.fusion import forced_mode
        from app.agents.nodes.affect_detection import fusion_drives_decision

        # Per-channel floors. A single global value misdescribes every channel with an override:
        # the geometry channel gates at 0.70 while the global sits at 0.50, so the monitor header
        # and the System Health tile both reported a threshold that channel never uses.
        channel_floors = {
            src: edges.min_confidence_for(src)
            for src in sorted(set(edges.DECISIVE_AFFECT_SOURCES) | set(edges._CHANNEL_MIN_CONFIDENCE))
        }

        return {
            "adaptStates": list(ADAPT_STATES),
            "adaptMinConfidence": ADAPT_MIN_CONFIDENCE,
            "channelMinConfidence": channel_floors,
            "adaptMinConsecutive": ADAPT_MIN_CONSECUTIVE,
            "adaptCooldownCycles": ADAPT_COOLDOWN_CYCLES,
            "fusionDrivesDecision": fusion_drives_decision(),
            "forcedMode": forced_mode(),
            # Which channels may trigger an intervention. `forcedMode` does NOT answer
            # this: it only skips fusion pairing, leaving every channel decisive.
            "decisiveAffectSources": list(edges.DECISIVE_AFFECT_SOURCES),
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


# ── per-session provenance ────────────────────────────────────────────────────────────
#
# Stamped once per learner connection as a `session_provenance` research event, so every
# session in the dataset carries the exact artifacts and settings that produced its readings.
# The deployed configuration has drifted from the code defaults more than once (model paths, the
# global floor, the LLM), and a snapshot taken by hand on one day says nothing about the session
# recorded the day after. Cheap by construction: file hashes are cached per (path, mtime, size) and
# no ONNX session is built, so it is safe on the connect path.

_HASH_CACHE: dict[tuple[str, float, int], str] = {}


def _sha256(path: str) -> str | None:
    import hashlib

    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (path, st.st_mtime, st.st_size)
    if key not in _HASH_CACHE:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        _HASH_CACHE[key] = digest.hexdigest()
    return _HASH_CACHE[key]


def provenance() -> dict[str, Any]:
    """Artifacts, effective gate configuration and LLM settings in force right now. Never raises."""
    out: dict[str, Any] = {}
    try:
        from app.agents.affect_mapping import _model_kind
        from app.services.behavioral_inference import _DEFAULT_MODEL_PATH

        facial_kind = _model_kind()
        facial_path = (
            os.getenv("GEOMETRY_MODEL_PATH", "models/engagenet_lean_gbdt.onnx")
            if facial_kind == "geometry"
            else os.getenv("AFFECT_MODEL_PATH", "models/cnn_lstm_confusion_anycut.onnx")
        )
        behavioral_path = os.getenv("BEHAVIORAL_MODEL_PATH", _DEFAULT_MODEL_PATH)
        out["models"] = {
            "facial": {"kind": facial_kind, "path": facial_path, "sha256": _sha256(facial_path)},
            "behavioral": {"path": behavioral_path, "sha256": _sha256(behavioral_path)},
        }
    except Exception as exc:
        out["models"] = {"error": f"{type(exc).__name__}: {exc}"}
    try:
        from dataclasses import asdict

        from app.services.config_service import get_config

        cfg = asdict(get_config())
        out["gate"] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in cfg.items()}
    except Exception as exc:
        out["gate"] = {"error": f"{type(exc).__name__}: {exc}"}
    try:
        from urllib.parse import urlparse

        from app.core.config import settings

        out["llm"] = {
            # Host only: the endpoint path is not informative and a URL can carry credentials.
            "endpoint_host": urlparse(settings.VLLM_ENDPOINT).hostname,
            "model": settings.VLLM_MODEL,
            "timeout_s": settings.VLLM_TIMEOUT_SECONDS,
            "max_tokens": settings.VLLM_MAX_TOKENS,
        }
    except Exception as exc:
        out["llm"] = {"error": f"{type(exc).__name__}: {exc}"}
    # Set by the deploy or the pilot compose file; absent in development.
    out["app_commit"] = os.getenv("APP_COMMIT") or None
    return out
