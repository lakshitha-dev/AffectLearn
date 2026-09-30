"""Export the pilot dataset: pseudonymised, one tidy file per channel, joinable on keys.

WHO IS INCLUDED
    Every learner with a `pilot_sessions` row (the facilitator started a sitting for them), minus
    demo accounts. Learner UUIDs are replaced by the participant code everywhere, and no e-mail,
    name or password leaves the database. The code -> person link exists only on paper.

WHAT IS WRITTEN (to --out, a directory)
    participants.csv   code, arm, phase, consent version and scopes, webcam, sitting start/end,
                       end reason, protocol version, config version at start
    timeline.csv       every research event of every participant, ordered by server time
                       (event_id, decision_id, code, event_type, timestamp, ..., payload as JSON)
    detections.csv     facial / behavioural / performance readings, flattened. These are MODEL
                       INFERENCES, not ground truth.
    decisions.csv      one row per gate verdict (`learner_profile_updated`), including the control
                       arm's shadow verdict, with the strategy and delivery joined on decision_id
    adaptations.csv    one row per delivered (or failed) card from the ledger, with when it was
                       first rendered, the learner's interaction, the probe answer and the outcome
    self_reports.csv   the learner's own feeling check-ins (a reference label, not ground truth)
    learning.csv       quiz and exercise attempts (server-graded) and assessment attempts
    instruments.csv    lesson feedback, SUS (with score) and UEQ-S (with scale means)
    raw_windows.jsonl  raw interaction windows, only for participants who opted in
    README.txt         this description, the export time and the config versions present

Usage (inside the api container):
    python -m scripts.export_pilot --out /app/pilot_export
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models.assessment import AssessmentAttempt
from app.models.assistance_event import AssistanceEvent
from app.models.instrument_response import InstrumentResponse
from app.models.pilot_session import PilotSession
from app.models.quiz_attempt import QuizAttempt
from app.models.raw_interaction_window import RawInteractionWindow
from app.models.research_event import ResearchEvent
from app.models.user import User
from app.services.consent import normalise_scopes
from app.services.instruments import sus_score, ueq_s_scales

DETECTION_TYPES = ("facial_affect_detected", "behavioral_affect_detected",
                   "performance_signal_detected")


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                             for k, v in row.items()})


async def _participants(db: AsyncSession) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """learner-id -> code, and one row per sitting. Demo accounts are never included."""
    sittings = (await db.execute(
        select(PilotSession, User).join(User, User.id == PilotSession.user_id)
        .where(User.is_demo.is_(False)).order_by(PilotSession.started_at)
    )).all()
    codes: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    for sitting, user in sittings:
        codes[str(user.id)] = sitting.participant_code
        rows.append({
            "code": sitting.participant_code, "arm": sitting.group, "phase": sitting.phase,
            "protocol_version": sitting.protocol_version,
            "consent_version": sitting.consent_version or user.consent_version,
            "consent_scopes": normalise_scopes(user.consent_scopes),
            "webcam_enabled": user.webcam_enabled,
            "consent_withdrawn_at": _iso(user.consent_withdrawn_at),
            "config_version_at_start": sitting.config_version_at_start,
            "started_at": _iso(sitting.started_at), "ended_at": _iso(sitting.ended_at),
            "end_reason": sitting.end_reason, "device": sitting.device,
            "deviation_notes": sitting.deviation_notes,
        })
    return codes, rows


def _flat_detection(e: ResearchEvent, code: str) -> dict[str, Any]:
    p = e.payload or {}
    return {
        "code": code, "event_id": e.event_id, "decision_id": e.decision_id,
        "event_type": e.event_type, "timestamp": e.timestamp,
        "received_at_ms": p.get("received_at_ms"),
        "client_window_start": (p.get("client_window") or [None, None])[0],
        "client_window_end": (p.get("client_window") or [None, None])[1],
        "session_id": e.session_id, "cycle_number": e.cycle_number, "section_id": e.section_id,
        "group": e.group, "config_version": e.config_version,
        "model_kind": p.get("model_kind"), "affect_source": p.get("affect_source"),
        "affect_state": p.get("affect_state"), "affect_confidence": p.get("affect_confidence"),
        "p_disengaged": p.get("p_disengaged"), "p_confused": p.get("p_confused"),
        "probs": p.get("probs"), "face_ratio": p.get("face_ratio"),
        "frames_with_face": p.get("frames_with_face"), "empty_cycle": p.get("empty_cycle"),
        "idle": p.get("idle"), "error": p.get("error"), "graph_ms": p.get("graph_ms"),
        "geometry_features": p.get("geometry_features"),
    }


async def export(db: AsyncSession, out: Path) -> dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    codes, participants = await _participants(db)
    learner_ids = list(codes)                        # research_events.learner_id is a string
    uuids = [uuid.UUID(lid) for lid in learner_ids]  # every other table keys on the UUID
    counts: dict[str, int] = {"participants": len(participants)}
    _write_csv(out / "participants.csv", participants, list(participants[0]) if participants else
               ["code"])

    events = (await db.execute(
        select(ResearchEvent).where(ResearchEvent.learner_id.in_(learner_ids))
        .order_by(ResearchEvent.timestamp, ResearchEvent.sequence_number)
    )).scalars().all() if learner_ids else []

    timeline = [{
        "event_id": e.event_id, "decision_id": e.decision_id, "code": codes[e.learner_id],
        "event_type": e.event_type, "timestamp": e.timestamp, "session_id": e.session_id,
        "sequence_number": e.sequence_number, "cycle_number": e.cycle_number,
        "course_id": e.course_id, "section_id": e.section_id, "block_id": e.block_id,
        "phase": e.phase, "group": e.group, "config_version": e.config_version,
        "payload": e.payload,
    } for e in events]
    _write_csv(out / "timeline.csv", timeline, list(timeline[0]) if timeline else ["event_id"])
    counts["timeline"] = len(timeline)

    detections = [_flat_detection(e, codes[e.learner_id]) for e in events
                  if e.event_type in DETECTION_TYPES]
    _write_csv(out / "detections.csv", detections,
               list(detections[0]) if detections else ["code"])
    counts["detections"] = len(detections)

    # One row per gate verdict, with what followed it in the same graph run.
    by_decision: dict[str, dict[str, ResearchEvent]] = defaultdict(dict)
    for e in events:
        if e.decision_id:
            by_decision[e.decision_id].setdefault(e.event_type, e)
    decisions = []
    for e in events:
        if e.event_type != "learner_profile_updated":
            continue
        p = e.payload or {}
        run = by_decision.get(e.decision_id or "", {})
        strategy = (run.get("strategy_decided").payload or {}) if run.get("strategy_decided") else {}
        delivered = run.get("adaptation_delivered")
        decisions.append({
            "code": codes[e.learner_id], "decision_id": e.decision_id, "timestamp": e.timestamp,
            "group": e.group, "section_id": e.section_id, "config_version": e.config_version,
            "affect_source": p.get("affect_source"), "affect_state": p.get("affect_state"),
            "affect_confidence": p.get("affect_confidence"),
            "min_confidence_applied": p.get("min_confidence_applied"),
            "decisive_channel": p.get("decisive_channel"),
            "gate": p.get("adaptation_gate"), "arm": p.get("arm"),
            "shadow_gate": p.get("shadow_gate"), "shadow_would_offer": p.get("shadow_would_offer"),
            "action": strategy.get("action_type"), "llm_model": strategy.get("llm_model"),
            "llm_ms": strategy.get("llm_ms"), "fallback": strategy.get("fallback"),
            "adaptation_id": (delivered.payload or {}).get("adaptation_id") if delivered else None,
            "delivered_at_ms": delivered.timestamp if delivered else None,
        })
    _write_csv(out / "decisions.csv", decisions, list(decisions[0]) if decisions else ["code"])
    counts["decisions"] = len(decisions)

    # Cards, from the ledger, with their lifecycle and the learner's answers joined on.
    rendered: dict[str, int] = {}
    probes: dict[str, dict[str, Any]] = {}
    for e in events:
        p = e.payload or {}
        if e.event_type == "adaptation_lifecycle" and p.get("event") == "rendered":
            rendered.setdefault(p.get("adaptation_id"), e.timestamp)
        if e.event_type == "adaptation_probe":
            probes[p.get("adaptation_id")] = p
    ledger = (await db.execute(
        select(AssistanceEvent).where(AssistanceEvent.learner_id.in_(uuids))
        .order_by(AssistanceEvent.created_at)
    )).scalars().all() if uuids else []
    adaptations = [{
        "code": codes[str(a.learner_id)], "adaptation_id": a.adaptation_id,
        "decision_id": a.decision_id, "section_id": str(a.section_id) if a.section_id else None,
        "group": a.group, "affect_state": a.affect_state, "affect_source": a.affect_source,
        "affect_confidence": a.affect_confidence, "gate_reason": a.gate_reason,
        "action_type": a.action_type, "generated": a.generated, "fallback": a.fallback,
        "delivered_at": _iso(a.delivered_at), "delivery_failed": a.delivery_failed,
        "rendered_at_ms": rendered.get(a.adaptation_id),
        "interaction": a.interaction, "interacted_at": _iso(a.interacted_at),
        "probe_response": (probes.get(a.adaptation_id) or {}).get("response"),
        "probe_dismissed": (probes.get(a.adaptation_id) or {}).get("dismissed"),
        "outcome_is_correct": a.outcome_is_correct,
    } for a in ledger]
    _write_csv(out / "adaptations.csv", adaptations,
               list(adaptations[0]) if adaptations else ["code"])
    counts["adaptations"] = len(adaptations)

    self_reports = [{
        "code": codes[e.learner_id], "timestamp": e.timestamp, "section_id": e.section_id,
        "cycle_number": e.cycle_number, "group": e.group,
        "affect": (e.payload or {}).get("affect"), "skipped": (e.payload or {}).get("skipped"),
        "prompt_index": (e.payload or {}).get("prompt_index"),
    } for e in events if e.event_type == "self_report"]
    _write_csv(out / "self_reports.csv", self_reports,
               list(self_reports[0]) if self_reports else ["code"])
    counts["self_reports"] = len(self_reports)

    learning: list[dict[str, Any]] = []
    for q in (await db.execute(select(QuizAttempt).where(QuizAttempt.user_id.in_(uuids))
                               .order_by(QuizAttempt.submitted_at))).scalars().all():
        learning.append({
            "code": codes[str(q.user_id)], "kind": "block_attempt",
            "block_id": str(q.content_block_id),
            "section_id": str(q.section_id) if q.section_id else None,
            "attempt_number": q.attempt_number, "is_correct": q.is_correct,
            "response_time_ms": q.response_time_ms, "assistance_id": q.assistance_id,
            "submitted_at": _iso(q.submitted_at),
        })
    for a in (await db.execute(select(AssessmentAttempt).where(AssessmentAttempt.user_id.in_(uuids))
                               .order_by(AssessmentAttempt.submitted_at))).scalars().all():
        learning.append({
            "code": codes[str(a.user_id)], "kind": "assessment",
            "assessment_id": str(a.assessment_id), "attempt_number": a.attempt_number,
            "score": a.score, "max_score": a.max_score, "started_at": _iso(a.started_at),
            "submitted_at": _iso(a.submitted_at),
        })
    _write_csv(out / "learning.csv", learning, [
        "code", "kind", "block_id", "section_id", "assessment_id", "attempt_number", "is_correct",
        "score", "max_score", "response_time_ms", "assistance_id", "started_at", "submitted_at"])
    counts["learning"] = len(learning)

    instruments = []
    for r in (await db.execute(select(InstrumentResponse)
                               .where(InstrumentResponse.user_id.in_(uuids))
                               .order_by(InstrumentResponse.submitted_at))).scalars().all():
        row = {"code": codes[str(r.user_id)], "instrument": r.instrument,
               "instrument_version": r.instrument_version, "context": r.context,
               "skipped": r.skipped, "shown_at": _iso(r.shown_at),
               "submitted_at": _iso(r.submitted_at), "responses": r.responses,
               "sus_score": None, "ueq_pragmatic": None, "ueq_hedonic": None, "ueq_overall": None}
        if r.instrument == "sus" and not r.skipped:
            row["sus_score"] = sus_score(r.responses)
        if r.instrument == "ueq_s" and not r.skipped:
            scales = ueq_s_scales(r.responses) or {}
            row.update(ueq_pragmatic=scales.get("pragmatic"), ueq_hedonic=scales.get("hedonic"),
                       ueq_overall=scales.get("overall"))
        instruments.append(row)
    _write_csv(out / "instruments.csv", instruments,
               list(instruments[0]) if instruments else ["code"])
    counts["instruments"] = len(instruments)

    windows = (await db.execute(select(RawInteractionWindow)
                                .where(RawInteractionWindow.learner_id.in_(uuids))
                                .order_by(RawInteractionWindow.capture_started_at_wall)
                                )).scalars().all() if uuids else []
    with (out / "raw_windows.jsonl").open("w", encoding="utf-8") as fh:
        for w in windows:
            fh.write(json.dumps({
                "code": codes[str(w.learner_id)], "session_id": w.session_id,
                "page_instance_id": w.page_instance_id, "cycle_number": w.cycle_number,
                "decision_id": w.decision_id, "section_id": w.section_id,
                "capture_started_at_wall": w.capture_started_at_wall,
                "capture_ended_at_wall": w.capture_ended_at_wall,
                "received_at_ms": w.received_at_ms, "schema_version": w.schema_version,
                "viewport": w.viewport, "events": w.events, "ui_events": w.ui_events,
                "dropped_events": w.dropped_events, "partial": w.partial,
            }) + "\n")
    counts["raw_windows"] = len(windows)

    config_versions = sorted({e.config_version for e in events if e.config_version is not None})
    (out / "README.txt").write_text(
        (__doc__ or "").strip() + "\n\n"
        f"Exported at: {datetime.now(timezone.utc).isoformat()}\n"
        f"Config versions present: {config_versions}"
        " (split every analysis by config_version if more than one)\n"
        f"Counts: {json.dumps(counts)}\n",
        encoding="utf-8",
    )
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the pseudonymised pilot dataset.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    async def run() -> None:
        async with async_session() as db:
            counts = await export(db, args.out)
        print(json.dumps(counts, indent=2))

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
