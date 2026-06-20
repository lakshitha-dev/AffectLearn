"""Tests for Pydantic Settings configuration."""



async def test_config_all_fields_present():
    """Verify all expected config fields exist on Settings."""
    from app.core.config import settings

    assert hasattr(settings, "DATABASE_URL")
    assert hasattr(settings, "REDIS_URL")
    assert hasattr(settings, "JWT_SECRET")
    assert hasattr(settings, "JWT_ALGORITHM")
    assert hasattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES")
    assert hasattr(settings, "REFRESH_TOKEN_EXPIRE_DAYS")
    assert hasattr(settings, "VLLM_ENDPOINT")


async def test_config_default_values():
    """Verify the declared code defaults, independent of any local `.env` override.

    `settings` is the live instance loaded from `.env`, so asserting against it makes
    this test environment-dependent (e.g. a dev `.env` may set REDIS_URL to localhost).
    The defaults live on the model fields, so check those.
    """
    from app.core.config import Settings

    defaults = {name: field.default for name, field in Settings.model_fields.items()}

    assert defaults["JWT_ALGORITHM"] == "HS256"
    assert defaults["ACCESS_TOKEN_EXPIRE_MINUTES"] == 30
    assert defaults["REFRESH_TOKEN_EXPIRE_DAYS"] == 7
    assert defaults["REDIS_URL"] == "redis://redis:6379"
    assert defaults["VLLM_ENDPOINT"] == "http://vllm:8080"


async def test_config_required_fields_loaded():
    """Verify required fields (no defaults) are loaded from env."""
    from app.core.config import settings

    assert settings.DATABASE_URL is not None
    assert len(settings.DATABASE_URL) > 0
    assert settings.JWT_SECRET is not None
    assert len(settings.JWT_SECRET) > 0
