"""Tests for the Redis cache graceful-degradation contract (Story 4.5 AC2).

No Redis runs in CI (REDIS_URL host is unresolvable), so these assert the calls degrade
to None/no-op without raising — never breaking a caller.
"""

import time

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


@pytest.mark.asyncio
async def test_ping_degrades_to_false_without_redis():
    redis_service._reset()
    assert await redis_service.ping() is False


@pytest.mark.asyncio
async def test_disable_is_a_cooldown_not_permanent():
    # A transient failure disables Redis for a COOLDOWN, then auto-recovers — it must NOT
    # latch off permanently (else one blip silently kills research draining for the process).
    redis_service._reset()
    redis_service._disable("simulated_blip")
    assert redis_service._disabled is True
    assert redis_service._disabled_until > 0          # a real failure sets a cooldown
    assert redis_service._get_client() is None         # within cooldown -> degraded
    redis_service._disabled_until = time.monotonic() - 1  # pretend the cooldown elapsed
    redis_service._get_client()                        # next attempt reconnects
    assert redis_service._disabled is False            # latch cleared -> recovered
    redis_service._reset()
