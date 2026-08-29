"""Thread sizing for ONNX Runtime sessions, aware of the container's real CPU quota.

Both inference services created `InferenceSession(...)` with no `SessionOptions`, so ORT sized its
thread pools itself. Inside a container that is the wrong default: ORT (like `os.cpu_count()`)
sees the HOST's core count, not the cgroup quota the App Service plan grants. On the B1 plan
(1 core) that means several intra-op threads per session, two sessions (facial CNN-LSTM +
behavioural GBDT), all contending for one throttled core.

Measured effect in production: `affect_detection` went from ~847ms to 12,000-15,000ms per cycle
once `AFFECT_DETECTION_MODE=auto` made both models run every cycle instead of one. Cycles are 30s,
so 15s of inference is half the budget and a slower cycle overlaps the next.

WHY NOT JUST PIN TO 1: that was the first attempt and it is wrong off the smallest plan. Measured
on a multi-core dev box, one 16-frame CNN-LSTM inference:

    ORT defaults          42.1 ms
    pinned to 1 thread   286.9 ms      <- 6.8x SLOWER

The problem is never "threads"; it is threads *in excess of the cores actually available*. So this
detects the real quota and sizes the pools to it — 1 on B1, more on a larger plan, unchanged on a
dev machine. `AFFECT_ONNX_THREADS` overrides when a deployment knows better.
"""

from __future__ import annotations

import os

import structlog

logger = structlog.get_logger(__name__)


def _cgroup_quota() -> float | None:
    """Effective CPU limit from cgroups, or None when not containerised / unlimited.

    cgroup v2: `/sys/fs/cgroup/cpu.max` -> "<quota> <period>" or "max <period>".
    cgroup v1: `cpu.cfs_quota_us` / `cpu.cfs_period_us`, quota -1 meaning unlimited.
    Never raises — an unreadable cgroup just means "fall back to the CPU count".
    """
    try:
        with open("/sys/fs/cgroup/cpu.max", encoding="utf-8") as fh:
            quota_s, period_s = fh.read().split()
        if quota_s != "max":
            period = float(period_s)
            if period > 0:
                return float(quota_s) / period
        return None
    except (OSError, ValueError):
        pass

    try:
        with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us", encoding="utf-8") as fh:
            quota = float(fh.read().strip())
        with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us", encoding="utf-8") as fh:
            period = float(fh.read().strip())
        if quota > 0 and period > 0:
            return quota / period
    except (OSError, ValueError):
        pass
    return None


def _available_cpus() -> int:
    """Cores this process may actually use. Always >= 1.

    Order matters: the cgroup quota is the binding limit in a container and is checked first;
    `sched_getaffinity` respects CPU pinning; `cpu_count` is the last resort and is the one that
    over-reports in containers.
    """
    quota = _cgroup_quota()
    if quota is not None and quota > 0:
        return max(1, int(quota))

    getaffinity = getattr(os, "sched_getaffinity", None)
    if getaffinity is not None:
        try:
            return max(1, len(getaffinity(0)))
        except OSError:
            pass

    return max(1, os.cpu_count() or 1)


def _thread_count() -> int:
    """Threads per ORT pool. `AFFECT_ONNX_THREADS` overrides the detected CPU quota."""
    override = os.getenv("AFFECT_ONNX_THREADS")
    if override:
        try:
            return max(1, int(override))
        except (TypeError, ValueError):
            logger.warning("invalid_affect_onnx_threads", value=override)
    return _available_cpus()


def session_options(ort):
    """`SessionOptions` sized to the available CPUs, or None if ORT cannot provide them.

    `ort` is passed in rather than imported here because both call sites import onnxruntime
    lazily, so this module keeps importing on machines without ORT (tests, tooling).

    Returning None is safe: the caller passes it straight to `InferenceSession(sess_options=None)`,
    which is exactly the previous default behaviour. Tuning threads must never block a model load.
    """
    n = _thread_count()
    try:
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = n   # threads WITHIN a single operator
        opts.inter_op_num_threads = n   # threads across independent operators
        logger.info("onnx_session_threads", threads=n)
        return opts
    except Exception:  # noqa: BLE001 — defensive; never block model load on thread tuning
        logger.warning("onnx_session_options_unavailable", threads=n, exc_info=True)
        return None
