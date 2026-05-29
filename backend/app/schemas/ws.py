"""Pydantic schemas for WebSocket messages.

Architecture exception (line 489): WebSocket message field names are **snake_case in both
directions** — distinct from the REST API's camelCase-on-the-wire convention. We therefore
extend pydantic.BaseModel directly (not CamelModel) so no alias generator is applied.

Per Story 4.1 Deviation 2: `system`-typed messages encode the sub-discriminator as an
`action` field (e.g. `{"type": "system", "action": "connected" | "error" | "session_restored"}`).
Non-system types use `type` alone (e.g. `heartbeat`, `heartbeat_ack`).
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class WSEnvelope(BaseModel):
    """Base envelope. Every WS message has at minimum `type` and `ts` (unix ms)."""

    type: str
    ts: int
    data: dict[str, Any] | None = None


class HeartbeatMessage(BaseModel):
    """Client → Server. Sent every 25s during idle."""

    type: Literal["heartbeat"]
    ts: int
    data: dict[str, Any] = Field(default_factory=dict)  # contains {"seq": <int>}


class HeartbeatAckMessage(BaseModel):
    """Server → Client. Echoes `seq` and adds `server_ts`."""

    type: Literal["heartbeat_ack"]
    ts: int
    data: dict[str, Any]


class ClientHelloMessage(BaseModel):
    """Optional client → server greeting. Reserved for future use; not required by Story 4.1."""

    type: Literal["client_hello"]
    ts: int
    data: dict[str, Any] | None = None


class SystemMessage(BaseModel):
    """Server → Client. `action` discriminator selects the system sub-type."""

    type: Literal["system"]
    action: Literal["connected", "error", "session_restored"]
    ts: int
    data: dict[str, Any] = Field(default_factory=dict)
