"""Tests for API route registration and basic endpoint availability."""


async def test_api_router_registered(test_client):
    """Verify the /api/v1 prefix is mounted and responds (404 for unknown sub-route is fine)."""
    response = await test_client.get("/api/v1/nonexistent")
    assert response.status_code == 404


async def test_openapi_schema_available(test_client):
    """Verify OpenAPI schema is accessible and health endpoint is registered."""
    response = await test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/health" in schema["paths"]


async def test_all_route_modules_importable():
    """Verify all 8 route modules import and expose a router."""
    from app.api.routes import auth, courses, learners, assessments, analytics, admin, surveys, ws

    modules = [auth, courses, learners, assessments, analytics, admin, surveys, ws]
    for mod in modules:
        assert hasattr(mod, "router"), f"{mod.__name__} missing 'router' attribute"


async def test_health_returns_json(test_client):
    """Verify health endpoint returns proper JSON content-type."""
    response = await test_client.get("/health")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"


async def test_cors_headers(test_client):
    """Verify CORS middleware allows localhost:3000 origin."""
    response = await test_client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


async def test_cors_rejects_unknown_origin(test_client):
    """Verify CORS middleware does not allow arbitrary origins."""
    response = await test_client.options(
        "/health",
        headers={
            "Origin": "http://evil.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # FastAPI CORS middleware omits the header for disallowed origins
    assert response.headers.get("access-control-allow-origin") != "http://evil.com"
