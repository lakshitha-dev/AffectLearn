"""Guards on how the vLLM client URL is assembled.

`llm.get_chat_client()` builds `base_url = f"{VLLM_ENDPOINT.rstrip('/')}/v1"` (llm.py:35). So
`VLLM_ENDPOINT` must be the bare origin — an operator who sets it to `http://host:8000/v1`
(the form that appears in most vLLM docs and curl examples) produces `/v1/v1`, every call 404s,
and `content_adapter` catches that as `vllm_error` and serves the SAME pre-written fallback copy
it serves when vLLM is absent entirely.

That is the trap worth a test: the misconfiguration is invisible. The symptom — generic canned
hints — is identical to "not deployed at all", which is the state production sat in undetected
until 2026-08-29. These tests make the URL contract explicit at the point of assembly.
"""

from __future__ import annotations

import pytest

from app.agents import llm as llm_mod
from app.core.config import settings


@pytest.fixture(autouse=True)
def reset_llm_singleton():
    llm_mod._reset()
    yield
    llm_mod._reset()


def test_default_endpoint_has_no_v1_suffix():
    """The shipped default must be a bare origin, so `/v1` is appended exactly once."""
    assert not settings.VLLM_ENDPOINT.rstrip("/").endswith("/v1")


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://vllm:8000",
        "http://vllm:8000/",
        "http://10.0.0.4:8000",
    ],
)
def test_base_url_appends_exactly_one_v1(monkeypatch, endpoint):
    monkeypatch.setattr(settings, "VLLM_ENDPOINT", endpoint)
    client = llm_mod.get_chat_client()
    base = str(getattr(client, "openai_api_base", None) or client.root_client.base_url)
    assert base.rstrip("/").endswith("/v1")
    assert "/v1/v1" not in base


def test_endpoint_with_v1_suffix_would_double_it(monkeypatch):
    """Documents the failure mode rather than silently tolerating it.

    If this ever starts failing because `llm.py` learned to strip a trailing `/v1`, that is an
    improvement — delete this test and keep the stripping.
    """
    monkeypatch.setattr(settings, "VLLM_ENDPOINT", "http://vllm:8000/v1")
    client = llm_mod.get_chat_client()
    base = str(getattr(client, "openai_api_base", None) or client.root_client.base_url)
    assert "/v1/v1" in base, (
        "llm.py appends /v1 unconditionally, so a /v1-suffixed endpoint doubles it. "
        "VLLM_ENDPOINT must be set to the bare origin."
    )
