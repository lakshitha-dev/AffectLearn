"""ConnectionManager — single in-process registry of active learner WebSocket sockets.

Architecture mandate: one persistent WebSocket per learner session (Story 4.1, AC #11).
When a second connection arrives for the same learner, the prior socket is closed with
code 4001 ("superseded") and replaced.

Thread-safety: FastAPI/uvicorn runs a single asyncio loop per worker, so `dict[str, WebSocket]`
mutation is safe under cooperative scheduling. The locking we do have (`asyncio.Lock`) only
serialises the *supersede* sequence to prevent two near-simultaneous connects from racing on
which one wins.
"""

import asyncio

import structlog
from fastapi import WebSocket

logger = structlog.get_logger(__name__)

WS_CLOSE_SUPERSEDED = 4001
WS_CLOSE_AUTH_FAILED = 4401


class ConnectionManager:
    """In-process registry of `user_id -> WebSocket`. One connection per learner."""

    def __init__(self) -> None:
        self._sockets: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket) -> bool:
        """Register a new socket for `user_id`. If a prior socket exists, close it with 4001.

        Returns True if a prior socket was superseded, False if this is a fresh connection.
        Must be called *after* `await websocket.accept()`.
        """
        superseded = False
        async with self._lock:
            prior = self._sockets.get(user_id)
            self._sockets[user_id] = websocket

        if prior is not None and prior is not websocket:
            superseded = True
            try:
                await prior.close(code=WS_CLOSE_SUPERSEDED, reason="superseded_by_new_connection")
            except Exception:
                logger.warning("supersede_close_failed", user_id=user_id)
        return superseded

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        """Remove the registered socket only if it *is* the one we hold.

        Prevents a race where supersede has already swapped in a newer socket and the
        prior socket's cleanup path would otherwise evict the active connection.
        """
        held = self._sockets.get(user_id)
        if held is websocket:
            del self._sockets[user_id]

    async def send_to(self, user_id: str, message: dict) -> bool:
        """Send a JSON message to a specific user. Returns False if no socket registered."""
        ws = self._sockets.get(user_id)
        if ws is None:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            logger.exception("send_to_failed", user_id=user_id, message_type=message.get("type"))
            return False

    def is_connected(self, user_id: str) -> bool:
        return user_id in self._sockets

    def active_user_ids(self) -> list[str]:
        return list(self._sockets.keys())


connection_manager = ConnectionManager()
