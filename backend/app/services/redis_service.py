"""Async Redis JSON cache with graceful degradation (Story 4.5).

The learner-profile hot path uses this. Redis being unreachable (CI, an outage, or the
`redis` package/host being absent) must NEVER break a learner's cycle (NFR22 spirit), so
every call degrades: `get_json` returns None, `set_json` no-ops. On the first failure the
client disables itself for the process so we don't pay repeated connect timeouts.
"""

from __future__ import annotations

import json
import os
from typing import Any

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

_client: Any | None = None
_disabled = False


def _get_client() -> Any | None:
    global _client, _disabled
    if _disabled:
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
            logger.warning("redis_unavailable_disabling_cache")
            _disabled = True
            return None
    return _client


def _disable(reason: str, **kw: Any) -> None:
    global _disabled
    _disabled = True
    logger.warning("redis_disabled", reason=reason, **kw)


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


def _reset() -> None:
    """Test helper — drop the cached client and re-enable."""
    global _client, _disabled
    _client = None
    _disabled = False
