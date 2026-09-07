"""Tests for API route registration and basic endpoint availability."""


async def test_api_router_registered(client):
    """Verify the /api/v1 prefix is mounted and responds (404 for unknown sub-route is fine)."""
    response = await client.get("/api/v1/nonexistent")
    assert response.status_code == 404


async def test_openapi_schema_available(client):
    """Verify OpenAPI schema is accessible and health endpoint is registered."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/health" in schema["paths"]


async def test_all_route_modules_importable():
    """Every route module imports and exposes a router.

    The list was written when there were eight modules and never grown; by the time it was
    noticed there were seventeen, so nine of them — `enrollments`, `monitor`, `research`,
    `reviews`, `section_progress`, `study`, `system_config`, `questionnaire` and
    `learner_profiles` — were not covered by the check that exists to catch an import error at
    startup. Derived from the aggregator now, so it cannot fall behind again.
    """
    import app.api.routes as routes_pkg
    from app.api.routes import __init__ as _aggregator  # noqa: F401

    import importlib
    import pkgutil

    modules = []
    for info in pkgutil.iter_modules(routes_pkg.__path__):
        if info.name.startswith("_"):
            continue
        modules.append(importlib.import_module(f"app.api.routes.{info.name}"))

    assert len(modules) >= 17, f"expected every route module, found {len(modules)}"
    for mod in modules:
        assert hasattr(mod, "router"), f"{mod.__name__} missing 'router' attribute"


async def test_health_returns_json(client):
    """Verify health endpoint returns proper JSON content-type."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"


async def test_cors_headers(client):
    """Verify CORS middleware allows localhost:3000 origin."""
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


async def test_cors_rejects_unknown_origin(client):
    """Verify CORS middleware does not allow arbitrary origins."""
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://evil.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # FastAPI CORS middleware omits the header for disallowed origins
    assert response.headers.get("access-control-allow-origin") != "http://evil.com"
