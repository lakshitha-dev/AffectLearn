"""Liveness endpoints: /health and the /health/pipeline data-collection monitor."""

import pytest


@pytest.mark.asyncio
async def test_health_ok(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_pipeline_health_shape(client):
    r = await client.get("/health/pipeline")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    for k in ("redis", "postgres", "worker"):
        assert k in body
    assert "running" in body["worker"] and "heartbeatAgeS" in body["worker"]
    assert isinstance(body["redis"], bool) and isinstance(body["postgres"], bool)
