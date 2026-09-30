"""The pilot export: pseudonymised, pilot participants only, and joinable on decision_id."""

import csv
import json
from datetime import datetime, timezone

import pytest

from app.core.security import hash_password
from app.models.assistance_event import AssistanceEvent
from app.models.instrument_response import InstrumentResponse
from app.models.pilot_session import PilotSession
from app.models.research_event import ResearchEvent
from app.models.user import Role, User
from scripts.export_pilot import export


async def _learner(db, email, *, demo=False):
    user = User(email_address=email, password_hash=hash_password("x" * 12), first_name="P001",
                last_name="Pilot", role=Role.learner, email_verified=True, is_demo=demo,
                consent_given_at=datetime.now(timezone.utc), consent_version="v1",
                consent_scopes={"behavioural": True, "raw_interaction": False})
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _event(user, etype, ts, payload, decision=None, **kw):
    return ResearchEvent(event_type=etype, learner_id=str(user.id), session_id="s1",
                         cycle_number=kw.get("cycle", 1), timestamp=ts, sequence_number=ts,
                         payload=payload, decision_id=decision, event_id=f"e-{etype}-{ts}",
                         group=kw.get("group", "adaptive"), config_version=3)


def _rows(path):
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.mark.asyncio
async def test_export_is_pseudonymised_and_joined(db, tmp_path):
    pilot = await _learner(db, "p001@pilot.affectlearn.io")
    outsider = await _learner(db, "someone@example.com")        # no sitting: not in the pilot
    demo = await _learner(db, "p999@pilot.affectlearn.io", demo=True)
    db.add(PilotSession(user_id=pilot.id, participant_code="P001", group="adaptive",
                        phase="phase_b", started_at=datetime.now(timezone.utc)))
    db.add(PilotSession(user_id=demo.id, participant_code="P999", group="control",
                        phase="phase_b", started_at=datetime.now(timezone.utc)))
    db.add_all([
        _event(pilot, "facial_affect_detected", 1000,
               {"affect_state": "bored", "affect_confidence": 0.83, "p_disengaged": 0.83,
                "model_kind": "geometry", "received_at_ms": 990,
                "client_window": [0, 990]}, decision="d-1"),
        _event(pilot, "learner_profile_updated", 1001,
               {"adaptation_gate": "ok", "arm": "delivered", "affect_source": "facial_geometry",
                "affect_state": "bored"}, decision="d-1"),
        _event(pilot, "strategy_decided", 1002,
               {"action_type": "increase_difficulty", "llm_model": "gpt-4o", "llm_ms": 2100},
               decision="d-1"),
        _event(pilot, "adaptation_delivered", 1003, {"adaptation_id": "ad-1"}, decision="d-1"),
        _event(pilot, "adaptation_lifecycle", 1004, {"adaptation_id": "ad-1", "event": "rendered"}),
        _event(pilot, "self_report", 1005, {"affect": "engaged", "skipped": False}),
        _event(outsider, "self_report", 1006, {"affect": "bored"}),
    ])
    db.add(AssistanceEvent(adaptation_id="ad-1", decision_id="d-1", learner_id=pilot.id,
                           session_id="s1", cycle_number=1, action_type="increase_difficulty",
                           delivered_at=datetime.now(timezone.utc)))
    db.add(InstrumentResponse(user_id=pilot.id, instrument="sus", instrument_version="1.0",
                              responses={f"q{i}": "3" for i in range(1, 11)}))
    await db.commit()

    counts = await export(db, tmp_path)

    assert counts["participants"] == 1                     # demo and outsider excluded
    everything = "".join(p.read_text(encoding="utf-8") for p in tmp_path.iterdir())
    for secret in (str(pilot.id), "pilot.affectlearn.io", "example.com", str(outsider.id)):
        assert secret not in everything, secret

    timeline = _rows(tmp_path / "timeline.csv")
    assert [r["timestamp"] for r in timeline] == sorted(r["timestamp"] for r in timeline)
    assert {r["code"] for r in timeline} == {"P001"}

    (decision,) = _rows(tmp_path / "decisions.csv")
    assert decision["decision_id"] == "d-1" and decision["gate"] == "ok"
    assert decision["action"] == "increase_difficulty" and decision["adaptation_id"] == "ad-1"

    (card,) = _rows(tmp_path / "adaptations.csv")
    assert card["decision_id"] == "d-1" and card["rendered_at_ms"] == "1004"

    (detection,) = _rows(tmp_path / "detections.csv")
    assert detection["affect_state"] == "bored" and detection["client_window_end"] == "990"

    (instrument,) = _rows(tmp_path / "instruments.csv")
    assert float(instrument["sus_score"]) == 50.0
    (participant,) = _rows(tmp_path / "participants.csv")
    assert participant["code"] == "P001" and participant["arm"] == "adaptive"
    assert json.loads(participant["consent_scopes"]) == {"behavioural": True,
                                                         "raw_interaction": False}
