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
import uuid as uuid_mod

import structlog
from fastapi import WebSocket

logger = structlog.get_logger(__name__)

WS_CLOSE_SUPERSEDED = 4001
WS_CLOSE_AUTH_FAILED = 4401


class ConnectionManager:
    """In-process registry of `user_id -> WebSocket`. One connection per learner.

    Tracks a stable `session_id` per `user_id` so research events emitted across
    same-user reconnects (network blip, supersede) join into a single learner
    session per AC #9. The session_id is kept alongside the socket registry but
    survives a disconnect — only `clear_session()` (called on explicit logout
    flows or test resets) removes it.
    """

    def __init__(self) -> None:
        self._sockets: dict[str, WebSocket] = {}
        self._session_ids: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self, user_id: str, websocket: WebSocket, preferred_session_id: str | None = None
    ) -> tuple[bool, str]:
        """Register a new socket for `user_id`. If a prior socket exists, close it with 4001.

        Returns `(superseded, session_id)`. `session_id` is reused across same-user
        reconnects so research events can correlate them. Must be called *after*
        `await websocket.accept()`.
        """
        superseded = False
        async with self._lock:
            prior = self._sockets.get(user_id)
            self._sockets[user_id] = websocket
            session_id = self._session_ids.get(user_id)
            if session_id is None:
                # This process has not seen the learner (first connect, or a restart). Reuse the
                # session the learner was in, when one is on record, so a redeploy mid-lesson does
                # not reset the escalation ladder and the cooldown.
                session_id = preferred_session_id or uuid_mod.uuid4().hex
                self._session_ids[user_id] = session_id

        if prior is not None and prior is not websocket:
            superseded = True
            try:
                await prior.close(code=WS_CLOSE_SUPERSEDED, reason="superseded_by_new_connection")
            except Exception:
                logger.warning("supersede_close_failed", user_id=user_id)
        return superseded, session_id

    def clear_session(self, user_id: str) -> None:
        """Drop the stored session_id for a user (e.g. on logout). Tests also use this."""
        self._session_ids.pop(user_id, None)

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

    def active_sessions(self) -> list[dict[str, str | None]]:
        """Currently-connected learners paired with their stable session id (Monitor)."""
        return [
            {"user_id": uid, "session_id": self._session_ids.get(uid)}
            for uid in self._sockets
        ]


connection_manager = ConnectionManager()
