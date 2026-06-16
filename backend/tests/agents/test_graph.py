"""End-to-end graph execution tests (Story 4.4 AC2/AC4).

Runs the compiled graph with `detect_engagement` faked, so no ONNX model is needed.
Verifies the Phase A path logs without adapting and the Phase B path traverses the
pedagogical stubs.
"""

import pytest

import app.agents.graph as graph_mod
import app.agents.llm as llm_mod
import app.agents.nodes.affect_detection as ad
import app.agents.nodes.content_adapter as ca
import app.agents.nodes.pedagogical as ped
from app.agents.graph import build_graph
from app.agents.state import make_initial_state

pytestmark = pytest.mark.asyncio


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FakeChatClient:
    """Stand-in for the vLLM client so the Phase B branch needs no GPU/network."""

    async def ainvoke(self, messages):
        return _FakeResp('{"action_type": "no_action", "reason": "ok", "urgency": "low"}')


@pytest.fixture
def fake_vllm(monkeypatch):
    """Mock the strategist's LLM call (Story 5.1) — node is real now, not a stub."""
    captured_events: list[dict] = []

    async def capture_emit(event):
        captured_events.append(event)

    monkeypatch.setattr(ped, "get_chat_client", lambda: _FakeChatClient())
    monkeypatch.setattr(ped, "emit_research_event", capture_emit)
    return captured_events

# Branch nodes whose traversal we want to OBSERVE (they are pass-through stubs that
# return {}, so without a spy the graph leaves no evidence of which path it took).
_BRANCH_NODES = (
    "log_only_node",
    "pedagogical_node",
    "content_adapter_node",
    "deliver_node",
)


@pytest.fixture
def traced(monkeypatch):
    """Compile a graph whose branch nodes record visits, proving the routed path.

    `build_graph` references these node functions as `graph` module globals, so
    patching them in `app.agents.graph` BEFORE building makes the compiled graph use
    the spies. Returns (compiled_graph, visited_list).
    """
    visited: list[str] = []

    def spy(name, original):
        async def _inner(state):
            visited.append(name)
            return await original(state)
        return _inner

    for attr in _BRANCH_NODES:
        short = attr.removesuffix("_node")
        monkeypatch.setattr(graph_mod, attr, spy(short, getattr(graph_mod, attr)))

    return build_graph().compile(), visited


@pytest.fixture
def compiled():
    # build a fresh graph per test (avoid the module singleton across tests)
    return build_graph().compile()


@pytest.fixture
def fake_engaged(monkeypatch):
    async def fake_detect(_data):
        return {"engagement_level": 2, "label": "high", "confidence": 0.8,
                "probs": [0.1, 0.1, 0.7, 0.1], "frames_used": 16}

    monkeypatch.setattr(ad, "detect_engagement", fake_detect)


async def test_phase_a_routes_to_log_only_no_adaptation(traced, fake_engaged):
    compiled, visited = traced
    state = make_initial_state(
        learner_id="u1", session_id="s1", cycle_number=1,
        facial_payload={"frames_b64": "x", "frames_captured": 30},
    )  # defaults phase_a / control
    out = await compiled.ainvoke(state)

    assert out["affect_state"] == "engaged"          # affect detected + written
    assert out["detection_mode"] == "facial_only"
    assert out["should_adapt"] is False
    # PROOF of routing: log_only was visited, the pedagogical branch was not.
    assert visited == ["log_only"]
    assert not out.get("strategy")                   # pedagogical branch NOT taken
    assert not out.get("adaptation_content")


async def test_phase_b_adaptive_traverses_pedagogical_branch(traced, fake_engaged, fake_vllm):
    compiled, visited = traced
    captured_events = fake_vllm
    state = make_initial_state(
        learner_id="u1", session_id="s1", cycle_number=1,
        facial_payload={"frames_b64": "x", "frames_captured": 30},
        phase="phase_b", group="adaptive",
    )
    out = await compiled.ainvoke(state)

    assert out["affect_state"] == "engaged"
    assert out["should_adapt"] is True
    # PROOF of routing: the full Phase B branch ran in order; log_only did NOT.
    assert visited == ["pedagogical", "content_adapter", "deliver"]
    assert "log_only" not in visited
    # Story 5.1: the strategist now writes a real strategy on this branch.
    assert out["strategy"]["action_type"] == "no_action"
    assert out["strategy"]["fallback"] is False
    # Story 5.3 / AC3: no_action produces no content and thus no delivery payload.
    assert not out.get("adaptation_content")
    assert not out.get("delivery_message")
    # AC7: strategy_decided research event must be emitted (AC5).
    strategy_events = [e for e in captured_events if e["event_type"] == "strategy_decided"]
    assert len(strategy_events) == 1
    assert strategy_events[0]["payload"]["action_type"] == "no_action"
    assert strategy_events[0]["payload"]["fallback"] is False


class _GenerativeChatClient:
    """vLLM stand-in returning a generative strategy then generative content."""

    def __init__(self):
        self.calls = 0

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:  # pedagogical strategist (expects JSON)
            return _FakeResp('{"action_type": "show_hint", "reason": "mild", "urgency": "medium"}')
        return _FakeResp("Here's a gentler way to think about it.")  # content adapter (plain text)


async def test_phase_b_generative_populates_adaptation_content(
    traced, fake_engaged, monkeypatch
):
    """A Phase B generative strategy reaches content_adapter and sets adaptation_content.

    Both LLM-calling nodes share the singleton client, so mocking `llm.get_chat_client`
    covers pedagogical + content_adapter; events are silenced. Topology/router unchanged.
    """
    llm_mod._reset()
    client = _GenerativeChatClient()
    monkeypatch.setattr(ped, "get_chat_client", lambda: client)
    monkeypatch.setattr(ca, "get_chat_client", lambda: client)

    async def noop_emit(event):
        return None

    monkeypatch.setattr(ped, "emit_research_event", noop_emit)
    monkeypatch.setattr(ca, "emit_research_event", noop_emit)

    compiled, visited = traced
    state = make_initial_state(
        learner_id="u1", session_id="s1", cycle_number=1,
        facial_payload={"frames_b64": "x", "frames_captured": 30},
        phase="phase_b", group="adaptive",
    )
    out = await compiled.ainvoke(state)

    assert visited == ["pedagogical", "content_adapter", "deliver"]
    assert out["strategy"]["action_type"] == "show_hint"
    content = out["adaptation_content"]
    assert content["text"] == "Here's a gentler way to think about it."
    assert content["variant"] == "show_hint"
    assert content["metadata"]["generated"] is True
    assert content["metadata"]["fallback"] is False
    # Story 5.3: the deliver node builds the WS wire payload into result_state.
    delivery = out["delivery_message"]
    assert delivery["type"] == "adaptation"
    assert delivery["action"] == "show_hint"
    assert delivery["content"] == {
        "text": "Here's a gentler way to think about it.",
        "variant": "show_hint",
    }
    assert isinstance(delivery["ts"], int)
    llm_mod._reset()


async def test_empty_cycle_flows_to_end_without_affect(compiled, monkeypatch):
    async def fake_detect(_data):
        return None

    monkeypatch.setattr(ad, "detect_engagement", fake_detect)
    state = make_initial_state(
        learner_id="u1", session_id="s1", cycle_number=1,
        facial_payload={"frames_b64": "", "frames_captured": 0},
    )
    out = await compiled.ainvoke(state)

    assert out.get("empty_cycle") is True
    assert "affect_state" not in out
