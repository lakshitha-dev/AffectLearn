"""Shared vLLM chat client for the agent nodes (Story 5.1).

The pedagogical strategist (Story 5.1) and the content adapter (Story 5.2) both call the
self-hosted fine-tuned Llama 3 8B through vLLM's OpenAI-compatible API (architecture lines
176-205, 442). Both use the SAME client config, so it is built once here as a lazy
process-wide singleton (mirroring `services.model_inference.get_model` and
`agents.graph.get_graph`) rather than reconnecting per node/cycle.

The endpoint, model, timeout, and token cap come from `settings` — never hardcoded
(architecture anti-pattern line 683). The OpenAI client needs a non-empty API key even
though vLLM ignores it, hence the `not-needed` default.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.core.config import settings

_CLIENT: ChatOpenAI | None = None


def get_chat_client() -> ChatOpenAI:
    """Return the process-wide vLLM chat client, constructing it on first use.

    Points `langchain-openai` at the vLLM endpoint's OpenAI-compatible `/v1` path.
    Per-call timeout is enforced exclusively by the caller via `asyncio.wait_for`, which
    raises `asyncio.TimeoutError` — the only timeout exception `_decide` handles as
    `fallback_reason="timeout"`. No client-level timeout is set here to avoid a race
    where `openai.APITimeoutError` fires first and is misclassified as `"vllm_error"`.
    """
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = ChatOpenAI(
            base_url=f"{settings.VLLM_ENDPOINT.rstrip('/')}/v1",
            api_key=settings.VLLM_API_KEY,
            model=settings.VLLM_MODEL,
            max_tokens=settings.VLLM_MAX_TOKENS,
            temperature=0.3,  # mostly deterministic pedagogical decisions
        )
    return _CLIENT


def _reset() -> None:
    """Test helper — drop the cached client so a test can re-stub configuration."""
    global _CLIENT
    _CLIENT = None
