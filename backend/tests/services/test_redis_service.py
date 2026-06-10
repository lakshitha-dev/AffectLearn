"""Tests for the Redis cache graceful-degradation contract (Story 4.5 AC2).

No Redis runs in CI (REDIS_URL host is unresolvable), so these assert the calls degrade
to None/no-op without raising — never breaking a caller.
"""

import pytest

from app.services import redis_service


@pytest.mark.asyncio
async def test_get_json_degrades_to_none_without_redis():
    redis_service._reset()
    assert await redis_service.get_json("profile:learner:nobody") is None


@pytest.mark.asyncio
async def test_set_json_no_ops_without_redis():
    redis_service._reset()
    await redis_service.set_json("profile:learner:nobody", {"a": 1})  # must not raise


@pytest.mark.asyncio
async def test_disabled_after_failure_returns_fast():
    redis_service._reset()
    await redis_service.get_json("k")          # first call fails -> disables
    assert redis_service._disabled is True
    assert await redis_service.get_json("k2") is None  # subsequent calls short-circuit
