"""Unit tests for the session pairing buffer (Story 4.4c AC3)."""

from app.services import fusion_buffer


def setup_function():
    fusion_buffer._reset()


def test_pair_within_window_returns_and_clears_counterpart():
    fusion_buffer.record("s1", "facial", {"confidence": 0.5}, 1000)
    # behavioral arrives ~1s later -> fetch the buffered facial result
    out = fusion_buffer.take_counterpart("s1", "behavioral", 2000)
    assert out == {"confidence": 0.5}
    # facial slot is consumed (no double-fusion)
    assert fusion_buffer.take_counterpart("s1", "behavioral", 2000) is None


def test_stale_counterpart_returns_none():
    fusion_buffer.record("s1", "facial", {"confidence": 0.5}, 1000)
    out = fusion_buffer.take_counterpart("s1", "behavioral", 1000 + 25_000)  # > 20s window
    assert out is None


def test_cross_session_isolation():
    fusion_buffer.record("s1", "facial", {"c": 1}, 1000)
    assert fusion_buffer.take_counterpart("s2", "behavioral", 1500) is None


def test_clear_session_drops_buffer():
    fusion_buffer.record("s1", "facial", {"c": 1}, 1000)
    fusion_buffer.clear_session("s1")
    assert fusion_buffer.take_counterpart("s1", "behavioral", 1500) is None
