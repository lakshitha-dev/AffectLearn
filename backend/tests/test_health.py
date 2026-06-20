async def test_app_starts():
    """Verify FastAPI app initializes without errors."""
    from app.main import app
    assert app.title == "AffectLearn API"


async def test_docs_endpoint(client):
    """Verify Swagger UI is accessible."""
    response = await client.get("/docs")
    assert response.status_code == 200


async def test_health_endpoint(client):
    """Verify health check endpoint responds."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


async def test_config_loads():
    """Verify pydantic settings load from environment."""
    from app.core.config import settings
    assert settings.DATABASE_URL is not None
    assert settings.JWT_SECRET is not None
