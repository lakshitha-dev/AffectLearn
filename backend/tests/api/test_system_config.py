"""Runtime configuration: the guarantees the settings page rests on.

Four things must hold, and three of them fail silently if they do not:

  * An empty config behaves EXACTLY as the deployment did before this feature existed. A settings
    table that quietly changed a threshold on first deploy would be the worst possible outcome.
  * An override reaches the gate without a restart — otherwise the page is decorative, which is
    what it was before.
  * `config_version` increments and lands on every event, so a threshold changed mid-collection is
    visible in the dataset instead of silently pooling incomparable cycles.
  * The API key is never returned by anything.
"""

from __future__ import annotations

import pytest

from app.services import config_service

BASE = "/api/v1/admin/config"

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clean_cache():
    config_service._reset()
    yield
    config_service._reset()


# ── defaults ──────────────────────────────────────────────────────────────────────────

async def test_an_empty_config_reports_the_deployed_defaults(client, db, admin_headers):
    """A fresh deploy must change nothing until someone deliberately changes something."""
    from app.agents import edges

    r = await client.get(BASE, headers=admin_headers)
    assert r.status_code == 200
    body = r.json()

    assert body["values"]["withholdRate"] == edges.ADAPT_WITHHOLD_RATE
    assert body["values"]["maxPerSession"] == edges.ADAPT_MAX_PER_SESSION
    assert body["values"]["minConsecutive"] == edges.ADAPT_MIN_CONSECUTIVE
    assert body["overridden"] == [], "nothing is overridden until an admin overrides it"
    assert body["locked"] is False
    assert body["version"] == 1


async def test_the_endpoint_is_admin_only(client, auth_headers):
    r = await client.get(BASE, headers=auth_headers)
    assert r.status_code == 403


# ── overrides reach the gate ──────────────────────────────────────────────────────────

async def test_an_override_changes_the_gate_without_a_restart(client, db, admin_headers):
    """The whole point. Before this, changing a threshold meant editing Azure and restarting."""
    from app.agents.edges import GATE_LOW_CONFIDENCE, passes_adaptation_gate

    r = await client.patch(BASE, headers=admin_headers,
                           json={"minConfidenceBehavioral": 0.95})
    assert r.status_code == 200, r.text
    assert r.json()["values"]["minConfidenceBehavioral"] == 0.95
    assert "minConfidenceBehavioral" in r.json()["overridden"]

    # A reading at 0.80 cleared the 0.70 default; against the new floor it must not.
    ok, reason = passes_adaptation_gate(
        affect_state="confused", affect_confidence=0.80,
        affect_history=["confused", "confused"], cycle_number=9,
        last_adaptation_cycle=None, affect_source="behavioral_model",
        config=config_service.get_config(),
    )
    assert (ok, reason) == (False, GATE_LOW_CONFIDENCE)


async def test_clearing_an_override_returns_the_setting_to_its_default(client, db, admin_headers):
    """Explicit null clears; it is NOT the same as writing the default's current value, because
    the default may later change and an override would pin it."""
    from app.agents import edges

    await client.patch(BASE, headers=admin_headers, json={"maxPerSession": 2})
    assert (await client.get(BASE, headers=admin_headers)).json()["values"]["maxPerSession"] == 2

    r = await client.patch(BASE, headers=admin_headers, json={"maxPerSession": None})
    assert r.json()["values"]["maxPerSession"] == edges.ADAPT_MAX_PER_SESSION
    assert "maxPerSession" not in r.json()["overridden"]


async def test_an_out_of_range_value_is_rejected(client, db, admin_headers):
    r = await client.patch(BASE, headers=admin_headers, json={"withholdRate": 1.5})
    assert r.status_code == 422


async def test_an_unknown_affect_state_is_rejected(client, db, admin_headers):
    r = await client.patch(BASE, headers=admin_headers,
                           json={"adaptStates": ["bored", "elated"]})
    assert r.status_code == 422


async def test_an_omitted_field_is_left_alone(client, db, admin_headers):
    """A partial PATCH must not reset every field the caller did not mention."""
    await client.patch(BASE, headers=admin_headers, json={"maxPerSession": 3})
    await client.patch(BASE, headers=admin_headers, json={"cooldownCycles": 5})

    values = (await client.get(BASE, headers=admin_headers)).json()["values"]
    assert values["maxPerSession"] == 3 and values["cooldownCycles"] == 5


# ── versioning ────────────────────────────────────────────────────────────────────────

async def test_the_version_increments_on_a_real_change(client, db, admin_headers):
    before = (await client.get(BASE, headers=admin_headers)).json()["version"]
    after = (await client.patch(BASE, headers=admin_headers,
                                json={"maxPerSession": 4})).json()["version"]
    assert after == before + 1


async def test_a_no_op_change_does_not_bump_the_version(client, db, admin_headers):
    """Bumping on a no-op would fragment the dataset at a boundary where nothing differs."""
    first = (await client.patch(BASE, headers=admin_headers,
                                json={"maxPerSession": 4})).json()["version"]
    second = (await client.patch(BASE, headers=admin_headers,
                                 json={"maxPerSession": 4})).json()["version"]
    assert second == first


async def test_the_version_lands_on_emitted_research_events(client, db, admin_headers, monkeypatch):
    """Without this a mid-study threshold change leaves no trace in the data."""
    from app.services import research_logger

    captured: list[dict] = []
    monkeypatch.setattr(research_logger.monitor_bus, "publish", lambda e: captured.append(e))

    await client.patch(BASE, headers=admin_headers, json={"maxPerSession": 4})
    await research_logger.emit({"event_type": "probe", "session_id": "s1", "timestamp": 1})

    probe = [e for e in captured if e["event_type"] == "probe"][0]
    assert probe["config_version"] == config_service.get_config().version


# ── the lock ──────────────────────────────────────────────────────────────────────────

async def test_a_locked_config_refuses_threshold_changes(client, db, admin_headers):
    await client.post(f"{BASE}/lock", headers=admin_headers, json={"locked": True})

    r = await client.patch(BASE, headers=admin_headers, json={"maxPerSession": 9})
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "CONFIG_LOCKED"


async def test_unlocking_restores_editability(client, db, admin_headers):
    await client.post(f"{BASE}/lock", headers=admin_headers, json={"locked": True})
    await client.post(f"{BASE}/lock", headers=admin_headers, json={"locked": False})

    r = await client.patch(BASE, headers=admin_headers, json={"maxPerSession": 9})
    assert r.status_code == 200
    assert r.json()["values"]["maxPerSession"] == 9


async def test_the_lock_state_is_reported(client, db, admin_headers):
    assert (await client.get(BASE, headers=admin_headers)).json()["locked"] is False
    await client.post(f"{BASE}/lock", headers=admin_headers, json={"locked": True})
    assert (await client.get(BASE, headers=admin_headers)).json()["locked"] is True


# ── the API key ───────────────────────────────────────────────────────────────────────

async def test_a_rotated_key_is_never_returned(client, db, admin_headers):
    """The guarantee that makes storing it acceptable at all."""
    secret = "sk-proj-supersecretvalue-9999"

    r = await client.put(f"{BASE}/llm-key", headers=admin_headers, json={"apiKey": secret})
    assert r.status_code == 200, r.text
    assert secret not in r.text
    assert r.json()["hint"] == "9999"

    full = await client.get(BASE, headers=admin_headers)
    assert secret not in full.text
    assert full.json()["llmKey"]["configured"] is True
    assert full.json()["llmKey"]["hint"] == "9999"


async def test_the_stored_key_round_trips_through_encryption(client, db, admin_headers):
    """It must be recoverable by the process, and only by the process."""
    secret = "sk-proj-roundtrip-1234"
    await client.put(f"{BASE}/llm-key", headers=admin_headers, json={"apiKey": secret})

    row = await config_service._row(db)
    assert row.llm_api_key_encrypted
    assert secret not in row.llm_api_key_encrypted, "must not be stored in the clear"

    decrypted = config_service._fernet().decrypt(
        row.llm_api_key_encrypted.encode("ascii")
    ).decode("utf-8")
    assert decrypted == secret


async def test_rotating_the_key_resets_the_cached_llm_client(client, db, admin_headers):
    """`get_chat_client` caches its client, so without a reset a rotation would look like it
    worked right up until the old key was revoked."""
    from app.agents import llm

    llm.get_chat_client()
    assert llm._CLIENT is not None

    await client.put(f"{BASE}/llm-key", headers=admin_headers, json={"apiKey": "sk-new-key-0001"})
    assert llm._CLIENT is None


async def test_a_too_short_key_is_rejected(client, db, admin_headers):
    r = await client.put(f"{BASE}/llm-key", headers=admin_headers, json={"apiKey": "abc"})
    assert r.status_code == 422


async def test_the_key_can_be_rotated_while_locked(client, db, admin_headers):
    """The lock protects the study's THRESHOLDS. A key rotation changes no measurement, and
    requiring an unlock to replace a compromised key would be the wrong trade."""
    await client.post(f"{BASE}/lock", headers=admin_headers, json={"locked": True})

    r = await client.put(f"{BASE}/llm-key", headers=admin_headers,
                         json={"apiKey": "sk-rotate-while-locked"})
    assert r.status_code == 200
