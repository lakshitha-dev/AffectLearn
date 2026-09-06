"""The session-start warm-up: keeping the cold call out of the first measured intervention.

A cold provider costs ~23s on this deployment against ~60ms warm. That matters here for a reason
beyond responsiveness: the outcome window starts at DELIVERY, so a cold first call sits between
the detection that triggered an intervention and the intervention arriving — and it does so in the
delivered arm only, because the withheld arm never calls a model. A systematic difference that
appears in one arm and not the other is indistinguishable from an effect.

So the warm-up is load-bearing, and its contract is that it can never make things worse: never
raises, never blocks a learner's connection.
"""

from __future__ import annotations

import asyncio

import pytest

import app.agents.llm as llm

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def reset_singleton():
    llm._reset()
    yield
    llm._reset()


class _Client:
    def __init__(self, *, exc=None, delay=0.0):
        self._exc, self._delay = exc, delay
        self.calls = 0

    async def ainvoke(self, messages):
        self.calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._exc:
            raise self._exc
        return type("R", (), {"content": "ok"})()


async def test_a_successful_warm_up_issues_exactly_one_call(monkeypatch):
    client = _Client()
    monkeypatch.setattr(llm, "get_chat_client", lambda: client)

    assert await llm.warm_up() is True
    assert client.calls == 1, "one throwaway completion, not a stream of them"


async def test_an_unreachable_provider_is_reported_not_raised(monkeypatch):
    """A missing model must not break a learner's connection — it only means the first real
    call pays the cost, which is the behaviour without a warm-up at all."""
    monkeypatch.setattr(llm, "get_chat_client",
                        lambda: _Client(exc=RuntimeError("connection refused")))

    assert await llm.warm_up() is False


async def test_a_hanging_provider_does_not_hang_the_warm_up(monkeypatch):
    """Bounded, so a wedged provider cannot leave the task alive for the whole session."""
    monkeypatch.setattr(llm, "_WARM_UP_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(llm, "get_chat_client", lambda: _Client(delay=5.0))

    assert await llm.warm_up() is False


async def test_a_client_that_cannot_even_be_constructed_is_survivable(monkeypatch):
    def _boom():
        raise RuntimeError("no endpoint configured")

    monkeypatch.setattr(llm, "get_chat_client", _boom)
    assert await llm.warm_up() is False
