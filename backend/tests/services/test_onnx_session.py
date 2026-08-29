"""Thread sizing must track the container's real CPU quota, not the host's core count.

The regression this guards against is subtle and was measured, not theorised: the first attempt at
fixing production's 12-15s inference pinned both ORT pools to 1 thread unconditionally. On a
multi-core machine that made one 16-frame CNN-LSTM inference 6.8x SLOWER (42ms -> 287ms). Too few
threads is as harmful as too many; only "threads == available cores" is right at both ends.
"""

from __future__ import annotations

import os

import pytest

from app.services import onnx_session


class _FakeOpts:
    def __init__(self):
        self.intra_op_num_threads = None
        self.inter_op_num_threads = None


class _FakeOrt:
    SessionOptions = _FakeOpts


def test_available_cpus_is_at_least_one():
    assert onnx_session._available_cpus() >= 1


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("AFFECT_ONNX_THREADS", "3")
    assert onnx_session._thread_count() == 3


@pytest.mark.parametrize("bad", ["0", "-4", "not-a-number", ""])
def test_invalid_override_falls_back_to_detected(monkeypatch, bad):
    """A junk override must never yield 0 or a negative pool size."""
    monkeypatch.setenv("AFFECT_ONNX_THREADS", bad)
    assert onnx_session._thread_count() >= 1


def test_session_options_sets_both_pools(monkeypatch):
    monkeypatch.setenv("AFFECT_ONNX_THREADS", "2")
    opts = onnx_session.session_options(_FakeOrt)
    assert opts.intra_op_num_threads == 2
    assert opts.inter_op_num_threads == 2


def test_never_pins_to_one_on_a_multicore_host(monkeypatch):
    """The exact regression: without an override, a multi-core host must not be pinned to 1."""
    monkeypatch.delenv("AFFECT_ONNX_THREADS", raising=False)
    monkeypatch.setattr(onnx_session, "_cgroup_quota", lambda: None)
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    monkeypatch.setattr(os, "sched_getaffinity", None, raising=False)
    assert onnx_session._thread_count() == 8


def test_cgroup_quota_beats_host_cpu_count(monkeypatch):
    """A B1-style 1-core quota must win over a host reporting many cores."""
    monkeypatch.delenv("AFFECT_ONNX_THREADS", raising=False)
    monkeypatch.setattr(onnx_session, "_cgroup_quota", lambda: 1.0)
    monkeypatch.setattr(os, "cpu_count", lambda: 16)
    assert onnx_session._thread_count() == 1


def test_returns_none_rather_than_raising_when_ort_lacks_options():
    """A model must still load if thread tuning is unavailable."""

    class _Broken:
        @staticmethod
        def SessionOptions():
            raise RuntimeError("unsupported build")

    assert onnx_session.session_options(_Broken) is None
