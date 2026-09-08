"""Is the vLLM endpoint that the pedagogical agents depend on actually reachable?

Nothing checked this before. When it was written the answer in production was NO: `VLLM_ENDPOINT`
defaulted to `http://vllm:8080`, a docker-compose service name that does not resolve on App
Service, so every strategy and content call timed out and fell back to
`fallbacks.rule_based_content`. Production now points at a hosted provider and generation
succeeds, which is why the probe has to authenticate: a keyless request to a provider that
authenticates returns 401 regardless of the key the application holds, and reporting that as a
credential failure is worse than not probing at all.

That degradation is deliberate and safe (a learner gets a canned hint rather than nothing), and
it IS recorded per-adaptation as `metadata.fallback=True`. But it was invisible at a glance:
an operator saw a green deploy and interventions being delivered, with no signal that none of
them were generated. This probe makes it a single field on the admin health payload.

Cached, because the admin dashboard polls health every 5s and a dead host costs a full timeout
per call. Never raises.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Short connect/read budget: this is a reachability probe on a health path, not a real call.
_PROBE_TIMEOUT_S = 1.5

_cache: dict[str, Any] | None = None
_cache_at: float = 0.0


def _reset_cache() -> None:
    """Test helper — drop the memoised probe result."""
    global _cache, _cache_at
    _cache, _cache_at = None, 0.0


async def probe(ttl_s: float = 10.0) -> dict[str, Any]:
    """Report vLLM reachability. Cached for `ttl_s`. Never raises.

    `reachable` is the operational bottom line: when it is False, adaptations are being served
    from the deterministic fallback rather than generated.
    """
    global _cache, _cache_at

    now = time.monotonic()
    if _cache is not None and (now - _cache_at) < ttl_s:
        return _cache

    endpoint = (settings.VLLM_ENDPOINT or "").rstrip("/")
    result: dict[str, Any] = {
        "endpoint": endpoint,
        "model": settings.VLLM_MODEL,
        "reachable": False,
        # Consequence spelled out so the dashboard does not have to infer it.
        "adaptationsGenerated": False,
    }

    if not endpoint:
        result["error"] = "VLLM_ENDPOINT is empty"
    else:
        try:
            import httpx

            # Send the credential the agents send. Without it a provider that
            # authenticates answers 401 to the probe whatever key the application
            # holds, so the probe reported a credential failure that did not exist
            # and the operator chased a working key. The header is harmless against
            # a local vLLM, which ignores it.
            headers = {}
            if settings.VLLM_API_KEY:
                headers["Authorization"] = f"Bearer {settings.VLLM_API_KEY}"
            async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S) as client:
                resp = await client.get(f"{endpoint}/v1/models", headers=headers)
            # `reachable` is about the HOST answering at all. Anything short of a 5xx means
            # something is there and serving.
            result["reachable"] = resp.status_code < 500
            result["status"] = resp.status_code

            # `adaptationsGenerated` is a DIFFERENT question, and conflating the two was wrong
            # for any provider that authenticates. `GET /v1/models` against OpenAI with a bad or
            # absent key returns 401, which is `< 500`, so this field read True while every
            # generation call failed auth and fell back to canned copy — the exact green-dashboard
            # blindness this probe exists to remove. A 4xx means reachable but NOT usable.
            result["adaptationsGenerated"] = resp.status_code < 400

            if resp.status_code in (401, 403):
                result["error"] = (
                    f"HTTP {resp.status_code}: endpoint reachable but rejected the credentials. "
                    "Adaptations are being served from the rule-based fallback."
                )
            elif resp.status_code >= 400:
                result["error"] = f"HTTP {resp.status_code}"
        except Exception as exc:
            # Unresolvable hostname, refused connection, or timeout all land here and all mean
            # the same thing operationally.
            result["error"] = f"{type(exc).__name__}: {exc}"

    _cache, _cache_at = result, now
    return result
