"""Async Redis JSON cache with graceful degradation (Story 4.5).

The learner-profile hot path uses this. Redis being unreachable (CI, an outage, or the
`redis` package/host being absent) must NEVER break a learner's cycle (NFR22 spirit), so
every call degrades: `get_json` returns None, `set_json` no-ops.

Failures disable Redis for a SHORT COOLDOWN (not permanently) and drop the client, so a
transient blip self-heals on the next attempt after the cooldown. This matters for the
research durability pipeline: a permanent latch would silently kill event draining +
buffering for the rest of the process on one timeout (the worker keeps polling and resumes
once Redis recovers). Cooldown length: `REDIS_COOLDOWN_S` (default 10s).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

_client: Any | None = None
_disabled = False           # True while unhealthy (during a cooldown, or pinned in tests)
_disabled_until = 0.0       # monotonic time the cooldown ends; 0 => pinned (no auto-recover)
_COOLDOWN_S = float(os.getenv("REDIS_COOLDOWN_S", "10"))


def _get_client() -> Any | None:
    global _client, _disabled, _disabled_until
    if _disabled:
        # Auto-recover once the cooldown has elapsed (a real failure always sets a cooldown;
        # a test-pinned `_disabled=True` leaves `_disabled_until=0` and stays disabled).
        if _disabled_until and time.monotonic() >= _disabled_until:
            _disabled = False
            _disabled_until = 0.0
            _client = None      # force a fresh reconnect
        else:
            return None
    if _client is None:
        try:
            import redis.asyncio as aioredis

            _client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
        except Exception:
            _disable("client_init_failed")
            return None
    return _client


def _disable(reason: str, **kw: Any) -> None:
    """Disable Redis for a cooldown and drop the client so the next attempt reconnects.

    A COOLDOWN, not a permanent latch — a transient blip must not permanently halt the
    research durability pipeline. Callers still degrade gracefully during the cooldown.
    """
    global _disabled, _disabled_until, _client
    _disabled = True
    _disabled_until = time.monotonic() + _COOLDOWN_S
    _client = None
    logger.warning("redis_disabled_cooldown", reason=reason, cooldown_s=_COOLDOWN_S, **kw)


async def get_json(key: str) -> dict | None:
    client = _get_client()
    if client is None:
        return None
    try:
        raw = await client.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        _disable("get_failed", key=key)
        return None


async def set_json(key: str, value: Any, ttl_seconds: int | None = None) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        data = json.dumps(value)
        if ttl_seconds:
            await client.set(key, data, ex=ttl_seconds)
        else:
            await client.set(key, data)
    except Exception:
        _disable("set_failed", key=key)


async def get_str(key: str) -> str | None:
    """Plain string read (no JSON). Degrades to None."""
    client = _get_client()
    if client is None:
        return None
    try:
        raw = await client.get(key)
        return raw if raw is None or isinstance(raw, str) else raw.decode()
    except Exception:
        _disable("get_failed", key=key)
        return None


async def set_str(key: str, value: str, ttl_seconds: int | None = None) -> bool:
    """Plain string write (no JSON). Returns False when Redis is unavailable."""
    client = _get_client()
    if client is None:
        return False
    try:
        if ttl_seconds:
            await client.set(key, value, ex=ttl_seconds)
        else:
            await client.set(key, value)
        return True
    except Exception:
        _disable("set_failed", key=key)
        return False


async def incr(key: str, ttl_seconds: int | None = None) -> int | None:
    """Atomic INCR, refreshing the key's TTL. Returns None when Redis is unavailable.

    Used for per-session research sequence numbers: an in-process counter restarts at 1 when
    the API restarts, while the session id it counts for is restored from Redis and survives --
    so the same (session_id, sequence_number) pair could be issued twice.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        value = await client.incr(key)
        if ttl_seconds:
            await client.expire(key, ttl_seconds)
        return int(value)
    except Exception:
        _disable("incr_failed", key=key)
        return None


async def delete_keys(*keys: str) -> int:
    """Delete the given keys. Returns how many existed; 0 when Redis is unavailable."""
    client = _get_client()
    if client is None or not keys:
        return 0
    try:
        return int(await client.delete(*keys))
    except Exception:
        _disable("delete_failed")
        return 0


async def delete_matching(pattern: str) -> int:
    """Delete every key matching a glob `pattern` (SCAN, not KEYS). 0 when unavailable."""
    client = _get_client()
    if client is None:
        return 0
    try:
        removed = 0
        async for key in client.scan_iter(match=pattern, count=500):
            removed += int(await client.delete(key))
        return removed
    except Exception:
        _disable("delete_matching_failed", pattern=pattern)
        return 0


async def exists(key: str) -> bool:
    """Whether `key` exists. False when Redis is unavailable."""
    client = _get_client()
    if client is None:
        return False
    try:
        return bool(await client.exists(key))
    except Exception:
        _disable("exists_failed", key=key)
        return False


# Cap the stream buffer (approximate trim) — the durable copy lives in Postgres, so the
# Redis Stream is only a hand-off buffer and must not grow unbounded (M1).
_STREAM_MAXLEN = int(os.getenv("RESEARCH_STREAM_MAXLEN", "100000"))


async def stream_add(stream: str, value: Any) -> str | None:
    """Append a JSON-encoded value to a Redis Stream (Story 4.7). Degrades to None.

    Trims to ~`_STREAM_MAXLEN` entries (approximate) so the buffer stays bounded.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        return await client.xadd(
            stream, {"data": json.dumps(value)}, maxlen=_STREAM_MAXLEN, approximate=True
        )
    except Exception:
        _disable("xadd_failed", stream=stream)
        return None


async def stream_read(
    stream: str, count: int = 100, last_id: str = "0"
) -> list[tuple[str, dict]]:
    """Read up to `count` entries after `last_id`. Returns [(entry_id, value)]; [] on error."""
    client = _get_client()
    if client is None:
        return []
    try:
        res = await client.xread({stream: last_id}, count=count)
        out: list[tuple[str, dict]] = []
        for _stream_name, entries in res or []:
            for entry_id, fields in entries:
                raw = fields.get("data")
                out.append((entry_id, json.loads(raw) if raw else {}))
        return out
    except Exception:
        _disable("xread_failed", stream=stream)
        return []


async def ping() -> bool:
    """Best-effort liveness ping. True if Redis responds; never raises (degrades to False)."""
    client = _get_client()
    if client is None:
        return False
    try:
        return bool(await client.ping())
    except Exception:
        _disable("ping_failed")
        return False


def _reset() -> None:
    """Test helper — drop the cached client and re-enable."""
    global _client, _disabled, _disabled_until
    _client = None
    _disabled = False
    _disabled_until = 0.0
