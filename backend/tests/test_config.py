"""Tests for Pydantic Settings configuration."""

import pytest


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
    """Verify config defaults are set correctly."""
    from app.core.config import settings

    assert settings.JWT_ALGORITHM == "HS256"
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 30
    assert settings.REFRESH_TOKEN_EXPIRE_DAYS == 7
    assert settings.REDIS_URL == "redis://redis:6379"
    assert settings.VLLM_ENDPOINT == "http://vllm:8080"


async def test_config_required_fields_loaded():
    """Verify required fields (no defaults) are loaded from env."""
    from app.core.config import settings

    assert settings.DATABASE_URL is not None
    assert len(settings.DATABASE_URL) > 0
    assert settings.JWT_SECRET is not None
    assert len(settings.JWT_SECRET) > 0
