"""Tests for the Monitor (observability dashboard) API: auth gating + payloads."""

from app.core.security import create_access_token
from app.services.monitor_bus import monitor_bus


# --- REST endpoints: admin-only -------------------------------------------------

async def test_graph_topology_requires_admin(client, admin_headers, auth_headers):
    # admin OK
    r = await client.get("/api/v1/monitor/graph", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    node_ids = {n["id"] for n in body["nodes"]}
    assert {"affect_detection", "learner_profiler", "log_only"} <= node_ids
    stubs = {n["id"] for n in body["nodes"] if n["kind"] == "stub"}
    # Story 5.1: `pedagogical` went active (vLLM strategy). Story 5.2: `content_adapter`
    # went active (vLLM content). Story 5.3: `deliver` went active (builds the WS
    # adaptation wire payload). No node is a stub anymore.
    assert stubs == set()
    assert "pedagogical" in node_ids
    assert "content_adapter" in node_ids
    deliver = next(n for n in body["nodes"] if n["id"] == "deliver")
    assert deliver["kind"] == "active"

    # learner forbidden
    r = await client.get("/api/v1/monitor/graph", headers=auth_headers)
    assert r.status_code == 403

    # unauthenticated rejected
    r = await client.get("/api/v1/monitor/graph")
    assert r.status_code in (401, 403)


async def test_health_reports_components(client, admin_headers):
    r = await client.get("/api/v1/monitor/health", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert "behavioral" in body["models"] and "facial" in body["models"]
    assert "available" in body["models"]["behavioral"]
    assert "ok" in body["database"]
    assert "enabled" in body["redis"]


async def test_events_returns_recent_buffer(client, admin_headers):
    monitor_bus.publish({"event_type": "behavioral_affect_detected", "session_id": "api-evt", "category": "domain"})
    r = await client.get("/api/v1/monitor/events", params={"session_id": "api-evt"}, headers=admin_headers)
    assert r.status_code == 200
    evs = r.json()["events"]
    assert evs and evs[-1]["event_type"] == "behavioral_affect_detected"


async def test_sessions_lists_recent(client, admin_headers):
    monitor_bus.publish({"event_type": "x", "session_id": "api-sess"})
    r = await client.get("/api/v1/monitor/sessions", headers=admin_headers)
    assert r.status_code == 200
    assert "api-sess" in r.json()["recent_session_ids"]


# --- SSE stream: auth gating (we don't drive the live loop here) ----------------

async def test_stream_requires_token(client):
    r = await client.get("/api/v1/monitor/stream")  # missing required ?token
    assert r.status_code == 422


async def test_stream_rejects_learner_token(client, test_user):
    token = create_access_token(str(test_user.id))
    r = await client.get("/api/v1/monitor/stream", params={"token": token})
    assert r.status_code == 403


async def test_stream_rejects_invalid_token(client):
    r = await client.get("/api/v1/monitor/stream", params={"token": "not-a-jwt"})
    assert r.status_code == 401


# --- health: shared model report + vLLM reachability (added with the admin monitor update) ---


async def test_health_reports_resolved_model_kind_not_just_presence(client, admin_headers):
    """`/monitor/health` used to report only `available`, from its OWN stale path defaults.

    It now shares `/health/pipeline`'s report, so a kind/artifact mismatch is visible here too.
    """
    from app.services import llm_health

    llm_health._reset_cache()
    body = (await client.get("/api/v1/monitor/health", headers=admin_headers)).json()

    for key in ("behavioral", "facial"):
        m = body["models"][key]
        assert "path" in m
        assert "exists" in m
        # Back-compat: the existing frontend reads `available`.
        assert m["available"] == bool(m["exists"])
    # The decision-path config travels with the models, so thresholds are auditable here.
    assert "decision" in body["models"]


async def test_health_surfaces_unreachable_llm_without_raising(client, admin_headers):
    """A dead vLLM must report, not 500 — and must say what it means for adaptations."""
    from app.services import llm_health

    llm_health._reset_cache()
    r = await client.get("/api/v1/monitor/health", headers=admin_headers)
    assert r.status_code == 200

    llm = r.json()["llm"]
    assert llm["reachable"] is False  # no vLLM in the test env
    assert llm["adaptationsGenerated"] is False
    assert "error" in llm
    assert "endpoint" in llm and "model" in llm


async def test_llm_probe_is_cached(client, admin_headers):
    """The dashboard polls health every 5s; a dead host must not cost a timeout each time."""
    from app.services import llm_health

    llm_health._reset_cache()
    first = await llm_health.probe()
    second = await llm_health.probe()
    assert first is second  # same object -> served from cache, no second network attempt
