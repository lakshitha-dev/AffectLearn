"""ConnectionManager unit tests (Story 4.1, Task 4.2)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.connection_manager import (
    WS_CLOSE_SUPERSEDED,
    ConnectionManager,
)


def _mock_ws() -> MagicMock:
    """A WebSocket stand-in with awaitable close/send_json."""
    ws = MagicMock()
    ws.close = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_connect_registers_socket():
    cm = ConnectionManager()
    ws = _mock_ws()

    superseded = await cm.connect("user-1", ws)

    assert superseded is False
    assert cm.is_connected("user-1")
    assert cm.active_user_ids() == ["user-1"]


@pytest.mark.asyncio
async def test_second_connect_supersedes_prior():
    cm = ConnectionManager()
    ws_a = _mock_ws()
    ws_b = _mock_ws()

    await cm.connect("user-1", ws_a)
    superseded = await cm.connect("user-1", ws_b)

    assert superseded is True
    ws_a.close.assert_awaited_once()
    args, kwargs = ws_a.close.await_args
    assert kwargs.get("code", args[0] if args else None) == WS_CLOSE_SUPERSEDED


@pytest.mark.asyncio
async def test_disconnect_only_removes_self():
    """If supersede already swapped in a new socket, prior socket's cleanup must not evict it."""
    cm = ConnectionManager()
    ws_a = _mock_ws()
    ws_b = _mock_ws()

    await cm.connect("user-1", ws_a)
    await cm.connect("user-1", ws_b)  # ws_a is now superseded; ws_b is current

    # ws_a's finally block fires AFTER supersede — must not delete the registry entry.
    cm.disconnect("user-1", ws_a)

    assert cm.is_connected("user-1") is True


@pytest.mark.asyncio
async def test_disconnect_clears_held_socket():
    cm = ConnectionManager()
    ws = _mock_ws()

    await cm.connect("user-1", ws)
    cm.disconnect("user-1", ws)

    assert cm.is_connected("user-1") is False


@pytest.mark.asyncio
async def test_send_to_returns_false_when_no_socket():
    cm = ConnectionManager()
    sent = await cm.send_to("user-1", {"type": "noop", "ts": 0})
    assert sent is False


@pytest.mark.asyncio
async def test_send_to_forwards_payload():
    cm = ConnectionManager()
    ws = _mock_ws()
    await cm.connect("user-1", ws)

    payload = {"type": "system", "action": "connected", "ts": 1, "data": {}}
    sent = await cm.send_to("user-1", payload)

    assert sent is True
    ws.send_json.assert_awaited_once_with(payload)


@pytest.mark.asyncio
async def test_concurrent_connects_serialise_via_lock():
    """Two near-simultaneous connects for the same user — last one wins, prior gets closed."""
    cm = ConnectionManager()
    ws_a = _mock_ws()
    ws_b = _mock_ws()

    results = await asyncio.gather(
        cm.connect("user-1", ws_a),
        cm.connect("user-1", ws_b),
    )

    # Exactly one of the two should report supersede=True (the second to enter the lock).
    assert sum(1 for r in results if r is True) == 1
    # And exactly one of the two sockets should have been closed.
    closed_count = (1 if ws_a.close.await_count else 0) + (1 if ws_b.close.await_count else 0)
    assert closed_count == 1
    # The registered socket is the one whose close was NOT called.
    assert cm.is_connected("user-1") is True
