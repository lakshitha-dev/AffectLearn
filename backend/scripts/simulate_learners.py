"""Simulated learners: drive the real pilot stack end to end, for a SYSTEM SIMULATION.

    ****************************************************************************************
    *  SIMULATED DATA. NOT PARTICIPANTS. NOT EVIDENCE ABOUT LEARNERS.                      *
    *  Report it only as a system simulation, never as pilot or participant results.       *
    ****************************************************************************************

WHAT IT IS FOR
    Before any real participant, this answers questions about the SYSTEM, using the same code path
    a browser uses (REST + the WebSocket, the real models, the real gate, the real LLM):
      * does every window reach Postgres, in order, with its event and decision ids?
      * how often does the gate offer help, per arm and learner profile, and why does it hold back?
      * how long from a reading to a card on screen, and how often does the LLM fall back?
      * does the control arm's shadow gate record matching "would have helped" moments?
      * does the stack cope with several learners at once for the length of a session?

WHAT IT IS NOT
    It cannot say whether adaptation helps anyone. The simulated learners' "true" states, their
    facial measurements, their behaviour and their reaction to help are all SCRIPTED here (see
    PROFILES and RESPONSE_MODEL). Agreement between the detectors and those scripted states only
    shows the plumbing works: the facial measurements were chosen, by probing the geometry model,
    to read as engaged or disengaged.

ISOLATION FROM PARTICIPANT DATA
    Simulated accounts are `sim001@simulation.affectlearn.io` ... and are flagged `is_demo`, so every
    research surface -- the admin exports, the monitor, gate replay and `scripts/export_pilot.py` --
    excludes them. No pilot sitting is ever created for them. `--cleanup` erases them afterwards.

Runs in real time: the gate's cooldown is measured on the server clock, so it cannot be sped up
without changing what it measures. Use inside the api container:

    python -m scripts.simulate_learners --learners 8 --minutes 15 --out /app/sim_report
    python -m scripts.simulate_learners --cleanup
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import websockets
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import async_session
from app.models.assistance_event import AssistanceEvent
from app.models.research_event import ResearchEvent
from app.models.user import Role, User
from app.services import data_rights_service, study_service
from app.services.consent import CURRENT_CONSENT_VERSION
from app.services.geometry_inference import GEOMETRY_CHANNEL_ORDER

SIM_DOMAIN = "simulation.affectlearn.io"
CYCLE_S = 30
STUDY_COURSE = "Building AI Agents"
BANNER = "SIMULATED DATA - NOT PARTICIPANTS - report only as a system simulation"

# Facial measurements the deployed geometry model reads as engaged / disengaged. Found by probing
# engagenet_lean_gbdt.onnx with synthetic frames (P(disengaged) ~0.05 vs ~0.99); they are chosen to
# drive the channel, not to imitate any real face.
GEOMETRY = {
    "engaged": {"gx": 0.0, "gy": -0.1, "gsd": 0.005, "mouth": 0.01, "motion": 0.0005},
    "disengaged": {"gx": -0.1, "gy": 0.1, "gsd": 0.03, "mouth": 0.1, "motion": 0.06},
}

# Scripted latent-state dynamics per profile: probability of each next state, per 30 s cycle.
PROFILES: dict[str, dict[str, dict[str, float]]] = {
    "steady": {"engaged": {"engaged": 0.92, "bored": 0.05, "confused": 0.03},
               "bored": {"engaged": 0.5, "bored": 0.45, "confused": 0.05},
               "confused": {"engaged": 0.5, "bored": 0.05, "confused": 0.45}},
    "drifting": {"engaged": {"engaged": 0.75, "bored": 0.22, "confused": 0.03},
                 "bored": {"engaged": 0.15, "bored": 0.82, "confused": 0.03},
                 "confused": {"engaged": 0.4, "bored": 0.3, "confused": 0.3}},
    "struggling": {"engaged": {"engaged": 0.7, "bored": 0.05, "confused": 0.25},
                   "bored": {"engaged": 0.3, "bored": 0.5, "confused": 0.2},
                   "confused": {"engaged": 0.15, "bored": 0.05, "confused": 0.8}},
    "mixed": {"engaged": {"engaged": 0.7, "bored": 0.15, "confused": 0.15},
              "bored": {"engaged": 0.3, "bored": 0.6, "confused": 0.1},
              "confused": {"engaged": 0.3, "bored": 0.1, "confused": 0.6}},
}

# ASSUMED reaction to a card (not measured anywhere): probability of accepting it, and of the scripted
# state then returning to engaged. It exists only so the loop behaves like a session; results that
# depend on it describe this assumption, not the system's effect on people.
RESPONSE_MODEL = {
    "accept": {"engaged": 0.6, "bored": 0.5, "confused": 0.7},
    "recover": {"bored": 0.5, "confused": 0.4},
    "probe": {"helped": 0.5, "unsure": 0.3, "did_not_help": 0.2},
}
NOT_PROBED = {"show_video", "skip_ahead", "suggest_break"}


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class Sim:
    code: str
    email: str
    password: str
    profile: str
    arm: str
    rng: random.Random
    state: str = "engaged"
    sent: Counter = field(default_factory=Counter)
    received: Counter = field(default_factory=Counter)
    states: Counter = field(default_factory=Counter)
    errors: list = field(default_factory=list)
    user_id: str = ""


# ── accounts ──────────────────────────────────────────────────────────────────


async def ensure_accounts(n: int, seed: int) -> list[Sim]:
    """Demo-flagged, consented, camera-on accounts; arms alternate so each profile is in both."""
    rng = random.Random(seed)
    profiles = list(PROFILES)
    sims: list[Sim] = []
    async with async_session() as db:
        await study_service.set_phase(db, "phase_b")
        for i in range(1, n + 1):
            code = f"SIM{i:03d}"
            email = f"sim{i:03d}@{SIM_DOMAIN}"
            profile = profiles[(i - 1) // 2 % len(profiles)]
            arm = "adaptive" if i % 2 else "control"
            password = f"sim-{uuid.uuid4().hex}"
            user = (await db.execute(select(User).where(User.email_address == email))).scalar_one_or_none()
            if user is None:
                user = User(email_address=email, password_hash=hash_password(password), first_name=code,
                            last_name="Simulated", role=Role.learner, email_verified=True, is_demo=True,
                            consent_given_at=datetime.now(timezone.utc),
                            consent_version=CURRENT_CONSENT_VERSION,
                            consent_scopes={"behavioural": True, "raw_interaction": True},
                            webcam_enabled=True)
                db.add(user)
            else:
                user.password_hash = hash_password(password)   # fresh credentials every run
                user.consent_withdrawn_at = None
            await db.commit()
            await db.refresh(user)
            try:
                await study_service.assign_group(db, user.id, arm)
            except Exception:   # a locked assignment keeps its arm
                arm = await study_service.get_group(db, user.id)
            sims.append(Sim(code, email, password, profile, arm,
                            random.Random(rng.randrange(1 << 30)), user_id=str(user.id)))
    return sims


async def cleanup() -> int:
    async with async_session() as db:
        users = (await db.execute(
            select(User).where(User.email_address.like(f"%@{SIM_DOMAIN}"))
        )).scalars().all()
        ids = [u.id for u in users]
    for uid in ids:
        async with async_session() as db:
            await data_rights_service.erase_learner(db, uid)
    return len(ids)


# ── synthetic signals ────────────────────────────────────────────────────────


def geometry_frames(state: str, rng: random.Random) -> tuple[list[list[float | None]], int]:
    """10 frames x 11 channels. Occasionally no face, as when a learner turns away."""
    look = GEOMETRY["disengaged" if state == "bored" else "engaged"]
    frames: list[list[float | None]] = []
    with_face = 0
    for _ in range(10):
        if rng.random() < (0.12 if state == "bored" else 0.02):
            row: list[float | None] = [None] * len(GEOMETRY_CHANNEL_ORDER)
            row[GEOMETRY_CHANNEL_ORDER.index("face_found")] = 0.0
            frames.append(row)
            continue
        with_face += 1
        values = {
            "yaw": rng.gauss(0, 4), "pitch": rng.gauss(0, 4), "roll": rng.gauss(0, 2),
            "ear_l": 0.28, "ear_r": 0.28, "ear_mean": 0.28,
            "mouth_open": max(0.0, rng.gauss(look["mouth"], 0.01)),
            "gaze_x": rng.gauss(look["gx"], look["gsd"]), "gaze_y": rng.gauss(look["gy"], look["gsd"]),
            "motion": max(0.0, rng.gauss(look["motion"], look["motion"] * 0.5)), "face_found": 1.0,
        }
        frames.append([values[c] for c in GEOMETRY_CHANNEL_ORDER])
    return frames, with_face


def behaviour_events(state: str, start: int, rng: random.Random) -> list[dict[str, Any]]:
    """30 s of mouse / key-category / scroll events in the browser's wire format."""
    events: list[dict[str, Any]] = []
    x, y, scroll = 600.0, 400.0, rng.randint(0, 2000)
    active = {"engaged": 0.8, "bored": 0.25, "confused": 0.6}[state]
    for tick in range(300):                       # 10 Hz
        t = start + tick * 100
        if rng.random() < active * 0.4:
            x = min(1500, max(0, x + rng.gauss(0, 25)))
            y = min(800, max(0, y + rng.gauss(0, 15)))
            events.append({"kind": "mouse_sample", "t_wall": t, "t_mono": tick * 100.0,
                           "x": round(x), "y": round(y)})
        if rng.random() < active * 0.03:
            back = state == "confused" and rng.random() < 0.45
            delta = -120 if back else 120
            scroll = max(0, scroll + delta)
            events.append({"kind": "scroll", "t_wall": t, "t_mono": tick * 100.0, "scroll_y": scroll,
                           "delta_y": delta, "direction": "up" if back else "down"})
        if rng.random() < active * 0.02:
            category = "backspace" if state == "confused" and rng.random() < 0.3 else "alpha"
            events.append({"kind": "key", "t_wall": t, "t_mono": tick * 100.0, "category": category})
        if rng.random() < 0.004:
            events.append({"kind": "mouse_click", "t_wall": t, "t_mono": tick * 100.0,
                           "x": round(x), "y": round(y), "button": 0, "target": "block-sim"})
    return events


def next_state(sim: Sim) -> str:
    row = PROFILES[sim.profile][sim.state]
    return sim.rng.choices(list(row), weights=list(row.values()))[0]


# ── one simulated learner ───────────────────────────────────────────────────


async def run_learner(sim: Sim, api: str, minutes: float) -> None:
    ws_url = api.replace("http", "ws", 1) + "/api/v1/ws"
    async with httpx.AsyncClient(base_url=f"{api}/api/v1", timeout=30) as http:
        login = await http.post("/auth/login", json={"emailAddress": sim.email, "password": sim.password})
        login.raise_for_status()
        token = login.json()["accessToken"]
        http.headers["Authorization"] = f"Bearer {token}"

        courses = (await http.get("/courses", params={"page": 1, "pageSize": 50})).json()["items"]
        course = next((c for c in courses if STUDY_COURSE in c["title"]), courses[0])
        await http.post("/enrollments", json={"courseId": course["id"]})
        detail = (await http.get(f"/courses/{course['id']}")).json()
        sections: list[dict] = []
        for module in detail.get("modules", []):
            for lesson in module.get("lessons", []):
                lesson_detail = (await http.get(f"/courses/lessons/{lesson['id']}/detail")).json()
                sections.extend(sorted(lesson_detail.get("sections", []), key=lambda s: s["sortOrder"]))
        if not sections:
            raise RuntimeError("study course has no sections - seed it first")

        async with websockets.connect(f"{ws_url}?token={token}", max_size=None) as ws:
            hello = json.loads(await ws.recv())
            adaptive = bool((hello.get("data") or {}).get("adaptive"))
            section_idx, cycle, reports = 0, 0, 0
            section = sections[0]

            async def send(kind: str, data: dict) -> None:
                await ws.send(json.dumps({"type": kind, "ts": now_ms(), "data": data}))
                sim.sent[kind] += 1

            async def respond(msg: dict) -> None:
                """Scripted reaction to a card: see it, then accept or dismiss, then maybe the probe."""
                aid, action = msg.get("adaptation_id"), msg.get("action")
                received = now_ms()
                await asyncio.sleep(sim.rng.uniform(0.5, 2))
                await send("adaptation_event", {"adaptation_id": aid, "action": action, "event": "rendered",
                                                "since_received_ms": now_ms() - received,
                                                "section_id": section["id"], "cycle_number": cycle})
                await asyncio.sleep(sim.rng.uniform(3, 12))
                accepted = sim.rng.random() < RESPONSE_MODEL["accept"][sim.state]
                await send("adaptation_interaction", {"adaptation_id": aid, "action": action,
                                                      "interaction": "accepted" if accepted else "dismissed",
                                                      "section_id": section["id"], "cycle_number": cycle})
                if accepted and sim.state in RESPONSE_MODEL["recover"] and \
                        sim.rng.random() < RESPONSE_MODEL["recover"][sim.state]:
                    sim.state = "engaged"
                if action not in NOT_PROBED:
                    await asyncio.sleep(max(0.0, 30 - (now_ms() - received) / 1000))
                    answers = RESPONSE_MODEL["probe"]
                    answer = sim.rng.choices(list(answers), weights=list(answers.values()))[0]
                    await send("adaptation_probe", {"adaptation_id": aid, "action": action,
                                                    "response": answer, "dismissed": False,
                                                    "shown_after_ms": now_ms() - received,
                                                    "section_id": section["id"], "cycle_number": cycle})

            reactions: set[asyncio.Task] = set()

            async def react(msg: dict) -> None:
                try:
                    await respond(msg)
                except (websockets.ConnectionClosed, asyncio.CancelledError):
                    pass    # the run ended while this card was still being "read"

            async def listen() -> None:
                async for raw in ws:
                    msg = json.loads(raw)
                    sim.received[msg.get("type", "?")] += 1
                    if msg.get("type") == "adaptation":
                        task = asyncio.create_task(react(msg))
                        reactions.add(task)
                        task.add_done_callback(reactions.discard)

            async def enter(idx: int) -> None:
                await send("ui_event", {"event": "section_entered", "section_id": sections[idx]["id"]})
                await http.post("/section-visits", json={"sectionId": sections[idx]["id"],
                                                         "entrySource": "next"})

            listener = asyncio.create_task(listen())
            await enter(0)
            deadline = time.time() + minutes * 60
            try:
                while time.time() < deadline:
                    window_start = now_ms()
                    await asyncio.sleep(CYCLE_S)
                    cycle += 1
                    sim.state = next_state(sim)
                    sim.states[sim.state] += 1
                    frames, with_face = geometry_frames(sim.state, sim.rng)
                    await send("facial_features", {
                        "cycle_number": cycle, "capture_started_at": window_start,
                        "capture_ended_at": now_ms(), "frames_captured": 10, "dropped_frames": 0,
                        "dropped_reasons": {"no_face": 10 - with_face, "low_confidence": 0},
                        "frames_with_face": with_face, "face_ratio": round(with_face / 10, 2),
                        "face_absent": with_face < 5, "geometry": frames, "contract_version": 1,
                        "geometry_contract_version": 1, "channel_order": list(GEOMETRY_CHANNEL_ORDER),
                        "frames_per_cycle": 10, "section_id": section["id"],
                    })
                    events = behaviour_events(sim.state, window_start, sim.rng)
                    await send("behavioral_window", {
                        "cycle_number": cycle, "capture_started_at_mono": 0.0,
                        "capture_ended_at_mono": 30000.0, "capture_started_at_wall": window_start,
                        "capture_ended_at_wall": window_start + 30000, "window_duration_ms": 30000,
                        "sampling_rate_hz": 10, "schema_version": 2, "events": events,
                        "summary": {"mouse_sample_count": sum(e["kind"] == "mouse_sample" for e in events),
                                    "mouse_click_count": sum(e["kind"] == "mouse_click" for e in events),
                                    "keystroke_count": sum(e["kind"] == "key" for e in events),
                                    "backspace_count": sum(e.get("category") == "backspace" for e in events),
                                    "scroll_event_count": sum(e["kind"] == "scroll" for e in events),
                                    "visibility_hidden_ms": 0, "idle": not events},
                        "dropped_events": 0, "section_id": section["id"], "page_instance_id": f"sim-{sim.code}",
                        "viewport": {"w": 1536, "h": 730, "doc_h": 3000, "dpr": 1.25}, "ui_events": [],
                    })
                    await send("heartbeat", {"seq": cycle})
                    if adaptive and sim.state == "confused" and sim.rng.random() < 0.15:
                        await send("help_request", {"request": "still_stuck", "section_id": section["id"],
                                                    "cycle_number": cycle})
                    if cycle % 4 == 0 and section_idx < len(sections) - 1:
                        await answer_quizzes(http, sim, section)
                        section_idx += 1
                        section = sections[section_idx]
                        await enter(section_idx)
                        if section_idx % 2 == 0:
                            reports += 1
                            await send("self_report", {"affect": sim.state, "skipped": False,
                                                       "prompt_index": reports, "section_id": section["id"],
                                                       "cycle_number": cycle})
            finally:
                listener.cancel()
                for task in list(reactions):
                    task.cancel()


async def answer_quizzes(http: httpx.AsyncClient, sim: Sim, section: dict) -> None:
    p_correct = {"engaged": 0.85, "bored": 0.6, "confused": 0.35}[sim.state]
    for block in section.get("contentBlocks", []):
        if block.get("blockType") != "quiz":
            continue
        options = (block.get("content") or {}).get("options") or []
        if not options:
            continue
        right = [o for o in options if o.get("isCorrect")]
        wrong = [o for o in options if not o.get("isCorrect")]
        pick = right if (sim.rng.random() < p_correct or not wrong) else [sim.rng.choice(wrong)]
        await http.post("/quiz-responses", json={
            "contentBlockId": block["id"], "selectedAnswers": [o["id"] for o in pick],
            "isCorrect": bool(pick and pick[0].get("isCorrect")),
            "responseTimeMs": int(sim.rng.uniform(4000, 30000)), "sectionId": section["id"]})
        sim.sent["quiz_response"] += 1


# ── report ────────────────────────────────────────────────────────────────────


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


async def build_report(sims: list[Sim], started_ms: int, ended_ms: int, out: Path) -> dict:
    by_id = {s.user_id: s for s in sims}
    async with async_session() as db:
        events = (await db.execute(
            select(ResearchEvent).where(ResearchEvent.learner_id.in_(list(by_id)),
                                        ResearchEvent.timestamp >= started_ms)
        )).scalars().all()
        ledger = (await db.execute(
            select(AssistanceEvent).where(AssistanceEvent.learner_id.in_(
                [uuid.UUID(u) for u in by_id]))
        )).scalars().all()
    hours = (ended_ms - started_ms) / 3_600_000
    per: dict[str, dict[str, Any]] = {}
    gate_reasons: dict[str, Counter] = defaultdict(Counter)
    shadow: Counter = Counter()
    latencies, llm_ms = [], []
    runs: dict[str, dict[str, ResearchEvent]] = defaultdict(dict)
    for e in events:
        if e.decision_id:
            runs[e.decision_id].setdefault(e.event_type, e)
    for s in sims:
        mine = [e for e in events if e.learner_id == s.user_id]
        types = Counter(e.event_type for e in mine)
        facial = [e for e in mine if e.event_type == "facial_affect_detected"]
        disengaged = sum((e.payload or {}).get("affect_state") == "bored" for e in facial)
        per[s.code] = {
            "profile": s.profile, "arm": s.arm, "scripted_states": dict(s.states),
            "facial_sent": s.sent["facial_features"], "facial_recorded": types["facial_affect_detected"],
            "behavioural_sent": s.sent["behavioral_window"],
            "behavioural_recorded": types["behavioral_affect_detected"],
            "facial_read_disengaged": disengaged,
            "cards_received": s.received["adaptation"],
            "offers_per_hour": round(s.received["adaptation"] / hours, 1) if hours else None,
            "missing_event_id": sum(1 for e in mine if not e.event_id),
            "errors": s.errors,
        }
        for e in mine:
            if e.event_type == "learner_profile_updated":
                p = e.payload or {}
                gate_reasons[s.arm][p.get("adaptation_gate")] += 1
                if p.get("shadow_would_offer"):
                    shadow[s.code] += 1
        per[s.code]["shadow_would_offer"] = shadow[s.code]
    for run in runs.values():
        detection = run.get("facial_affect_detected") or run.get("behavioral_affect_detected")
        delivered = run.get("adaptation_delivered")
        if detection and delivered and (detection.payload or {}).get("received_at_ms"):
            latencies.append((delivered.timestamp - detection.payload["received_at_ms"]) / 1000)
        strategy = run.get("strategy_decided")
        if strategy and (strategy.payload or {}).get("llm_ms") is not None:
            llm_ms.append(strategy.payload["llm_ms"])
    chains = [r for r in runs.values() if "adaptation_delivered" in r]
    complete = sum(1 for r in chains if "learner_profile_updated" in r and "strategy_decided" in r and
                   ("facial_affect_detected" in r or "behavioral_affect_detected" in r or
                    "help_requested" in r))
    report = {
        "banner": BANNER,
        "started": datetime.fromtimestamp(started_ms / 1000, timezone.utc).isoformat(),
        "minutes": round((ended_ms - started_ms) / 60000, 1),
        "learners": len(sims),
        "response_model_assumed": RESPONSE_MODEL,
        "per_learner": per,
        "totals": {
            "facial_sent": sum(p["facial_sent"] for p in per.values()),
            "facial_recorded": sum(p["facial_recorded"] for p in per.values()),
            "behavioural_sent": sum(p["behavioural_sent"] for p in per.values()),
            "behavioural_recorded": sum(p["behavioural_recorded"] for p in per.values()),
            "events_recorded": len(events),
            "events_missing_event_id": sum(p["missing_event_id"] for p in per.values()),
            "cards_delivered": len(chains),
            "cards_with_complete_decision_chain": complete,
            "ledger_rows": len(ledger),
            "ledger_rows_with_decision_id": sum(1 for a in ledger if a.decision_id),
            "llm_fallbacks": sum(1 for a in ledger if a.fallback),
        },
        "gate_reasons_by_arm": {arm: dict(c.most_common()) for arm, c in gate_reasons.items()},
        "actions": dict(Counter(a.action_type for a in ledger).most_common()),
        "reading_to_card_seconds": {"median": _pct(latencies, 0.5), "p90": _pct(latencies, 0.9),
                                     "n": len(latencies)},
        "llm_ms": {"median": _pct(llm_ms, 0.5), "p90": _pct(llm_ms, 0.9), "n": len(llm_ms)},
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "simulation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "SIMULATION_REPORT.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def render_markdown(r: dict) -> str:
    t = r["totals"]
    lines = [
        f"# System simulation report\n\n**{r['banner']}.**\n",
        f"{r['learners']} scripted learners, {r['minutes']} minutes, started {r['started']}. Every "
        "state, facial measurement, behaviour and reaction to help is scripted "
        "(`scripts/simulate_learners.py`). This report describes the system, not learners.\n",
        "## Data completeness\n",
        "| Measure | Value |", "|---|---|",
        f"| Facial windows recorded / sent | {t['facial_recorded']} / {t['facial_sent']} |",
        f"| Behavioural windows recorded / sent | {t['behavioural_recorded']} / {t['behavioural_sent']} |",
        f"| Research events recorded | {t['events_recorded']} (missing event_id: {t['events_missing_event_id']}) |",
        f"| Cards delivered | {t['cards_delivered']} (complete decision chain: {t['cards_with_complete_decision_chain']}) |",
        f"| Ledger rows with decision_id | {t['ledger_rows_with_decision_id']} / {t['ledger_rows']} |",
        f"| LLM fallbacks | {t['llm_fallbacks']} |",
        "\n## Timing\n",
        f"- Reading received -> card delivered: median {r['reading_to_card_seconds']['median']} s, "
        f"p90 {r['reading_to_card_seconds']['p90']} s (n = {r['reading_to_card_seconds']['n']})",
        f"- LLM strategy call: median {r['llm_ms']['median']} ms, p90 {r['llm_ms']['p90']} ms "
        f"(n = {r['llm_ms']['n']})",
        "\n## Gate verdicts by arm\n",
    ]
    for arm, reasons in r["gate_reasons_by_arm"].items():
        lines.append(f"- **{arm}**: " + ", ".join(f"{k} {v}" for k, v in reasons.items()))
    lines += ["\n## Actions delivered\n", ", ".join(f"{k} {v}" for k, v in r["actions"].items()) or "none",
              "\n## Per scripted learner\n",
              "| Code | Profile | Arm | Facial rec/sent | Read disengaged | Cards | Offers/h | Shadow offers |",
              "|---|---|---|---|---|---|---|---|"]
    for code, p in r["per_learner"].items():
        lines.append(f"| {code} | {p['profile']} | {p['arm']} | {p['facial_recorded']}/{p['facial_sent']} | "
                     f"{p['facial_read_disengaged']} | {p['cards_received']} | {p['offers_per_hour']} | "
                     f"{p['shadow_would_offer']} |")
    lines += ["\n## How to read this\n",
              "- Completeness, ids, latency and gate reasons describe the running system and can be "
              "reported as a system simulation.",
              "- Offer rates depend on the scripted profiles; they show how the gate paces help for "
              "these inputs, not how often real learners will be helped.",
              "- Nothing here measures learning, engagement or whether help works: the reaction to "
              f"help is an assumption ({json.dumps(r['response_model_assumed'])}).\n"]
    return "\n".join(lines)


async def main_async(args) -> int:
    if args.cleanup:
        print(f"erased {await cleanup()} simulated account(s)")
        return 0
    sims = await ensure_accounts(args.learners, args.seed)
    print(f"{BANNER}\nrunning {len(sims)} scripted learners for {args.minutes} min (real time)")
    for s in sims:
        print(f"  {s.code}  profile={s.profile:<10} arm={s.arm}")
    started = now_ms()

    async def guarded(s: Sim):
        try:
            await run_learner(s, args.api, args.minutes)
        except Exception as exc:   # one learner failing must not stop the others
            s.errors.append(f"{type(exc).__name__}: {exc}")
            print(f"  {s.code} stopped: {type(exc).__name__}: {exc}")

    await asyncio.gather(*(guarded(s) for s in sims))
    await asyncio.sleep(5)          # let the worker drain the last events
    report = await build_report(sims, started, now_ms(), Path(args.out))
    t = report["totals"]
    print(f"done. facial {t['facial_recorded']}/{t['facial_sent']}, behavioural "
          f"{t['behavioural_recorded']}/{t['behavioural_sent']}, cards {t['cards_delivered']}; "
          f"report in {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scripted learners for a SYSTEM SIMULATION "
                                                 "(not participant data).")
    parser.add_argument("--learners", type=int, default=8)
    parser.add_argument("--minutes", type=float, default=15)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--api", default=os.getenv("SIM_API", "http://localhost:8000"))
    parser.add_argument("--out", default="/app/sim_report")
    parser.add_argument("--cleanup", action="store_true", help="erase every simulated account")
    return asyncio.run(main_async(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
