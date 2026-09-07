"""The declared topology must match the graph that actually runs.

`api/routes/monitor.py` used to carry a second, hand-written copy of `build_graph`: the same six
nodes and eight edges, maintained separately. Two descriptions of one structure drift, and the
drift is silent — the observability dashboard keeps rendering a diagram, just not of the graph
that is executing, which is the one failure mode an observability tool must not have.

The monitor now derives from `app.agents.graph`. These tests are what stops the declaration
itself from drifting from the wiring below it.
"""

from app.agents.graph import EDGES, NODE_IDS, STUB_NODES, build_graph
from app.api.routes.monitor import _NODE_PRESENTATION, _graph_topology


def test_declared_nodes_match_the_compiled_graph():
    """A node added to `build_graph` without the declaration fails here, not on the dashboard."""
    compiled = build_graph().compile()
    graph_nodes = set(compiled.get_graph().nodes)

    # LangGraph includes the START/END sentinels in its node set; the declaration covers the
    # nodes that do work.
    assert set(NODE_IDS) == graph_nodes - {"__start__", "__end__"}


def test_declared_edges_match_the_compiled_graph():
    compiled = build_graph().compile()
    actual = {
        (edge.source, edge.target)
        for edge in compiled.get_graph().edges
    }

    def normalise(name: str) -> str:
        return {"START": "__start__", "END": "__end__"}.get(name, name)

    declared = {(normalise(e["from"]), normalise(e["to"])) for e in EDGES}

    assert declared == actual


def test_every_node_has_dashboard_presentation():
    """A node with no label renders as its raw id, which is a worse diagram than a wrong one."""
    missing = [node_id for node_id in NODE_IDS if node_id not in _NODE_PRESENTATION]
    assert missing == [], f"nodes with no label/description: {missing}"


def test_topology_payload_marks_stub_nodes_from_the_graphs_own_declaration():
    payload = _graph_topology()
    kinds = {node["id"]: node["kind"] for node in payload["nodes"]}

    for node_id in NODE_IDS:
        expected = "stub" if node_id in STUB_NODES else "active"
        assert kinds[node_id] == expected


def test_topology_payload_shape_is_unchanged():
    """The dashboard contract: nodes carry id/label/kind/desc, edges carry from/to."""
    payload = _graph_topology()

    assert set(payload) == {"nodes", "edges"}
    for node in payload["nodes"]:
        assert set(node) == {"id", "label", "kind", "desc"}
    for edge in payload["edges"]:
        assert {"from", "to"} <= set(edge)
        # `kind`/`route` appear only on the conditional edges, never as nulls.
        assert set(edge) <= {"from", "to", "kind", "route"}


def test_conditional_edges_are_marked_as_such():
    payload = _graph_topology()
    conditional = [e for e in payload["edges"] if e.get("kind") == "conditional"]

    # The profiler is the only branch point in the loop: log-only vs the adaptive path.
    assert {e["to"] for e in conditional} == {"log_only", "pedagogical"}
    assert all(e["from"] == "learner_profiler" for e in conditional)
