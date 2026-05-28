"""Accelerated stability test for the WebSocket handler (Story 4.1, Task 4.6).

The full 60-minute stability check runs manually pre-pilot. This CI-friendly variant
performs 60 simulated heartbeat round-trips back-to-back and asserts every one is
ack'd with a matching seq.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.services.connection_manager import connection_manager


HEARTBEAT_CYCLES = 60


@pytest.fixture(autouse=True)
def _reset_manager_after_each_test():
    yield
    connection_manager._sockets.clear()


@pytest.fixture
def sync_client(db: AsyncSession, monkeypatch):
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "SEED_ON_STARTUP", False)

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_sixty_heartbeat_cycles_no_drops(sync_client: TestClient, test_user: User):
    """60 sequential heartbeat round-trips — proxy for the 60-min continuous-uptime AC."""
    token = create_access_token(str(test_user.id))
    with sync_client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        _ = ws.receive_json()  # discard initial system.connected

        for seq in range(1, HEARTBEAT_CYCLES + 1):
            ws.send_json({"type": "heartbeat", "ts": seq * 1000, "data": {"seq": seq}})
            ack = ws.receive_json()
            assert ack["type"] == "heartbeat_ack", f"cycle {seq}: expected ack, got {ack}"
            assert ack["data"]["seq"] == seq, f"cycle {seq}: seq mismatch"
            assert "server_ts" in ack["data"]
