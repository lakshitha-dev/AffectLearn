"""Graph-wrapper latency micro-benchmark (Story 4.4 AC8 / Task 8.7).

Measures end-to-end `ainvoke` latency with faked inference (no ONNX), so this isolates
the graph + state-plumbing overhead — the CNN-LSTM's own <200ms CPU budget is verified
separately (ml-training-guide-daisee.md §13) and added on top once the real artifact is
placed at AFFECT_MODEL_PATH. This commits the AC8 measurement as a reproducible test
(it was previously only recorded as prose in the Dev Agent Record).

The asserted ceiling is deliberately generous so it is not flaky on slow/loaded CI; the
printed median/p95 are the real signal (~1-3ms wrapper overhead on a dev machine).
"""

import statistics
import time

import pytest

import app.agents.nodes.affect_detection as ad
from app.agents.graph import build_graph
from app.agents.state import make_initial_state

pytestmark = pytest.mark.asyncio

N_CYCLES = 30                 # AC8 requires N >= 20
WRAPPER_CEILING_MS = 100.0    # generous CI-safe bound; real overhead is a few ms


async def test_graph_wrapper_latency_under_budget(monkeypatch, capsys):
    async def fake_detect(_data):
        return {"engagement_level": 2, "label": "high", "confidence": 0.8,
                "probs": [0.1, 0.1, 0.7, 0.1], "frames_used": 16}

    monkeypatch.setattr(ad, "detect_engagement", fake_detect)
    compiled = build_graph().compile()

    samples_ms: list[float] = []
    for i in range(N_CYCLES):
        state = make_initial_state(
            learner_id="u1", session_id="s1", cycle_number=i,
            facial_payload={"frames_b64": "x", "frames_captured": 30},
        )
        t0 = time.perf_counter()
        await compiled.ainvoke(state)
        samples_ms.append((time.perf_counter() - t0) * 1000.0)

    samples_ms.sort()
    median = statistics.median(samples_ms)
    p95 = samples_ms[max(0, int(len(samples_ms) * 0.95) - 1)]

    with capsys.disabled():
        print(f"\n[AC8] graph wrapper over {N_CYCLES} cycles: "
              f"median={median:.2f}ms p95={p95:.2f}ms (fake inference)")

    # Wrapper overhead must be negligible against the 200ms full-cycle NFR1 budget.
    assert median < WRAPPER_CEILING_MS, f"wrapper median {median:.2f}ms exceeds budget"


async def test_behavioral_graph_latency_under_budget(monkeypatch, capsys):
    """Story 4.4b AC7 — full behavioral cycle (incl. feature extraction) wrapper cost.

    Uses a fake behavioral session so no ONNX artifact is needed; this still exercises
    the real event->DataFrame adapter + feature_engineering on each cycle.
    """
    import numpy as np

    import app.agents.nodes.affect_detection as ad
    import app.services.behavioral_inference as bi

    fake_model = bi.BehavioralModel(
        session=type("S", (), {"run": lambda self, _o, f: [np.array([[2.0, 0.1, 0.1, 0.1]], np.float32)]})(),
        stats={"mean": np.zeros(13, np.float32), "std": np.ones(13, np.float32)},
    )
    monkeypatch.setattr(bi, "get_behavioral_model", lambda: fake_model)
    # node imported predict_from_window by reference; keep it pointed at the real fn
    monkeypatch.setattr(ad, "predict_from_window", bi.predict_from_window)

    compiled = build_graph().compile()
    # Realistic active window (~400 events): 300 mouse samples (10Hz×30s) + clicks/keys/scrolls.
    events = [{"kind": "mouse_sample", "t_wall": 100 * i, "x": 500 + (i % 50), "y": 400} for i in range(300)]
    events += [{"kind": "mouse_click", "t_wall": 1000 * i} for i in range(15)]
    events += [{"kind": "key", "t_wall": 800 * i, "category": "alpha"} for i in range(60)]
    events += [{"kind": "scroll", "t_wall": 1200 * i, "delta_y": 40 if i % 2 else -40} for i in range(25)]
    payload = {"events": events, "capture_started_at_wall": 0,
               "summary": {"idle": False}}

    samples_ms: list[float] = []
    for i in range(N_CYCLES):
        state = make_initial_state(
            learner_id="u1", session_id="s1", cycle_number=i, behavioral_payload=payload,
        )
        t0 = time.perf_counter()
        await compiled.ainvoke(state)
        samples_ms.append((time.perf_counter() - t0) * 1000.0)

    samples_ms.sort()
    median = statistics.median(samples_ms)
    p95 = samples_ms[max(0, int(len(samples_ms) * 0.95) - 1)]
    with capsys.disabled():
        print(f"\n[AC7] behavioral cycle over {N_CYCLES} cycles: "
              f"median={median:.2f}ms p95={p95:.2f}ms (fake session, real feature extraction)")

    assert median < WRAPPER_CEILING_MS, f"behavioral median {median:.2f}ms exceeds budget"
