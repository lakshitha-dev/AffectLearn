"""Drive the WHOLE loop, every affect state at every ladder rung, and print what comes out.

WHY THIS EXISTS
---------------
Nothing joined the two halves. `replay_session.py` replays real event streams and stops at the
gate; `try_llm_adaptation.py` starts after it, with `should_adapt` set by hand. So the question
this script answers had no tool: given a learner in a given state, at a given depth, what does the
system ACTUALLY decide and deliver?

That question is not academic. The only live session anyone has looked at produced 13 cycles, 3
interventions, and all three were `skip_ahead` -- which under the rule ladder means rung >= 1 on
every one of them. Five of the eight action types have never been observed at all. The action
distribution this prints is the direct measurement of that.

WHAT IT RUNS
------------
The compiled graph, in process:

    affect_detection -> learner_profiler -> (gate) -> pedagogical -> content_adapter -> deliver

In process rather than over a WebSocket because there is no WS client in `requirements.txt`, and
adding a dependency to run a script buys nothing here: the socket hop is covered by the dev
endpoint (`POST /dev/simulate-cycle`) and by `e2e/adaptation-delivery.spec.ts`. What this covers
that neither of those does is the DECISION, across the whole grid, in one table.

Affect is pre-seeded into the state. With no payload the detection node reports an empty cycle and
returns no affect keys, so LangGraph's merge leaves the seeded values in place and the node it
would otherwise run -- the one the thesis reports on -- is left exactly as it is.

WHAT IT DELIBERATELY DOES NOT TOUCH
-----------------------------------
The stored configuration. The gate settings are primed into `config_service`'s in-process cache
and never written, so this never modifies the database it is measuring and needs no restore step.
`frustrated` is enabled FOR THIS RUN ONLY; the deployment's `ADAPT_STATES` is unchanged and the
output says plainly which actions that makes unreachable in reality.

USAGE
-----
    python scripts/drive_adaptations.py                 # rule ladder (no model configured)
    VLLM_ENDPOINT=... VLLM_MODEL=... VLLM_API_KEY=... \
    VLLM_TIMEOUT_SECONDS=60 python scripts/drive_adaptations.py

No database is required: it runs against an in-memory SQLite, so the profiler's cold path and the
content adapter's variant lookup both degrade the way they do when Postgres is unreachable. Point
`DATABASE_URL` at a real database to exercise designer-authored variants as well.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections import Counter
from pathlib import Path

import structlog

# The graph emits a trace per node, and one of them contains "->" as U+2192. On a Windows console
# stdout defaults to cp1252, which cannot encode it, and the resulting UnicodeEncodeError inside
# the logger propagates out of the node and kills the run -- so the script died on the first row
# with a stack trace about a character, not about adaptations.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Those same per-node traces bury the table this script exists to print. The app configures no
# structlog processors of its own, so the default logger prints everything; filter to warnings for
# this process only.
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "script-only-not-a-real-secret")

from app.agents import edges  # noqa: E402
from app.agents.fallbacks import ACTION_TYPES  # noqa: E402
from app.agents.graph import get_graph  # noqa: E402
from app.agents.state import make_initial_state  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services import config_service, profile_service, redis_service  # noqa: E402

#: A section with enough substance that a vague answer is visibly vague. Same one
#: `try_llm_adaptation.py` uses, so the two scripts' output is comparable.
SECTION = {
    "section_id": "script-section",
    "topic": "TCP three-way handshake",
    "lesson": "Establishing a connection",
    "difficulty": "unknown",
    "body": (
        "TCP opens a connection with a three-way handshake. The client sends a SYN carrying its "
        "initial sequence number. The server replies with SYN-ACK, acknowledging the client's "
        "number and sending its own. The client answers with ACK. Only then does data flow. "
        "The third packet exists so the server learns that the client received its reply; "
        "without it the server would have to commit resources to a connection that may never "
        "have been requested by a real client."
    ),
}

#: Every state that can trigger, at every depth its ladder has. Together these reach all eight
#: actions. `engaged` is included at rung 0 because "the system leaves an engaged learner alone"
#: is a claim worth seeing hold rather than assuming.
GRID: list[tuple[str, int]] = [
    ("confused", 0), ("confused", 1), ("confused", 2),
    ("bored", 0), ("bored", 1),
    ("frustrated", 0), ("frustrated", 1), ("frustrated", 2),
    ("engaged", 0),
]


def prime_config(*, withhold: float) -> None:
    """Install gate settings for this process only.

    Written straight into `config_service`'s cache rather than through `set_values`, which would
    persist a row and bump the version stamped on every research event the deployment writes
    afterwards. A script that measures the gate must not change what it is measuring.

    `frustrated` is added to `adapt_states` HERE and nowhere else -- see `unreachable_note`.
    """
    config_service._cache = config_service._build(
        {
            "adaptStates": ("bored", "confused", "frustrated"),
            "withholdRate": withhold,
            "maxPerSession": 999,
            "cooldownCycles": 0,
            "minConsecutive": edges.ADAPT_MIN_CONSECUTIVE,
        },
        version=config_service.get_config().version,
        locked=False,
    )


def unreachable_note() -> list[str]:
    """What this run proves, and what it does not.

    A green table is otherwise indistinguishable from a working capability, and on this deployment
    three of the eight actions cannot occur at any confidence, for two independent reasons.
    """
    lines: list[str] = []
    deployed_states = tuple(edges.ADAPT_STATES)
    if "frustrated" not in deployed_states:
        lines.append(
            f"ADAPT_STATES on this deployment is ({', '.join(deployed_states)}). `frustrated` is "
            f"enabled FOR THIS RUN ONLY, so show_encouragement, simplify and suggest_break appear "
            f"below and cannot occur organically."
        )
    lines.append(
        "Separately, no deployed detector emits `frustrated` at all: the geometry channel and the "
        "aggregate GBDT do not have the class. Enabling the state would not by itself make those "
        "three actions reachable."
    )
    return lines


def build_state(affect: str, cycle: int) -> dict:
    state = make_initial_state(
        learner_id="script-learner",
        session_id="script-session",
        cycle_number=cycle,
        phase="phase_b",
        group="adaptive",
        content_context=SECTION,
    )
    state["affect_state"] = affect
    state["affect_confidence"] = 0.95
    state["affect_source"] = edges.AFFECT_SOURCE_BEHAVIORAL
    state["detection_mode"] = "behavioral_only"
    return state


def seed_profile(affect: str, rung: int, skill: str) -> dict:
    """The profile the gate reads: per-source history for the sustain check, and the rung.

    Per-SOURCE, not the interleaved `affect_history`. The graph runs once per modality, so the
    interleaved list's last entries are usually two channels disagreeing inside one cycle;
    `profile_service.sustain_history` reads the per-source list for exactly that reason, and
    seeding the wrong one makes every row below say `not_sustained`.
    """
    need = max(1, config_service.get_config().min_consecutive)
    profile = profile_service.default_profile()
    profile["skill_level"] = skill
    profile["affect_state"] = affect
    profile["affect_history"] = [affect] * need
    profile["affect_history_by_source"] = {edges.AFFECT_SOURCE_BEHAVIORAL: [affect] * need}
    for _ in range(rung):
        edges.record_delivered_rung(profile, "script-session", SECTION["section_id"], affect)
    profile["eligible_this_session"] = 0
    return profile


async def run_one(affect: str, rung: int, cycle: int, skill: str) -> dict:
    # The profiler loads from Redis first and Postgres second. Patching the read is how the
    # profile gets in without a running Redis and without writing to anyone's real profile --
    # this script is a measurement, not a session.
    profile = seed_profile(affect, rung, skill)
    original_get, original_set = redis_service.get_json, redis_service.set_json

    async def fake_get(key: str):
        return profile if key.startswith("profile:learner:") else await original_get(key)

    async def fake_set(key: str, value, ttl_seconds=None):
        return None

    redis_service.get_json, redis_service.set_json = fake_get, fake_set
    try:
        result = await get_graph().ainvoke(build_state(affect, cycle))
    finally:
        redis_service.get_json, redis_service.set_json = original_get, original_set

    strategy = result.get("strategy") or {}
    content = result.get("adaptation_content") or {}
    metadata = content.get("metadata") or {}
    message = result.get("delivery_message") or {}
    return {
        "affect": affect,
        "rung": rung,
        "gate": result.get("adaptation_gate_reason"),
        "action": message.get("action") or strategy.get("action_type"),
        "strategy_fallback": bool(strategy.get("fallback")),
        "content_fallback": bool(metadata.get("fallback")),
        "fallback_reason": metadata.get("fallback_reason"),
        "authored_variant": bool(metadata.get("authored_variant")),
        "text": (message.get("content") or {}).get("text"),
    }


def print_row(row: dict) -> None:
    print(f"\n  {row['affect'].upper():<11} rung {row['rung']}")
    print(f"    gate       : {row['gate']}")
    print(f"    action     : {row['action'] or 'none'}")
    if row["strategy_fallback"]:
        print("    !! the DECISION came from the rule ladder, not the model")
    if row["content_fallback"]:
        print(f"    !! the TEXT came from canned copy, not the model "
              f"(reason: {row['fallback_reason']})")
    if row["authored_variant"]:
        print("    (served a designer-authored variant; the model was not asked)")
    if row["text"]:
        print(f"    delivered  : {' '.join(row['text'].split())[:200]}")
    else:
        print("    delivered  : nothing")


def print_summary(rows: list[dict]) -> None:
    delivered = [r for r in rows if r["action"]]
    actions = Counter(r["action"] for r in delivered)
    gates = Counter(r["gate"] for r in rows)

    print()
    print("=" * 92)
    print("ACTION DISTRIBUTION")
    print("=" * 92)
    for action in ACTION_TYPES:
        if action == "no_action":
            continue
        count = actions.get(action, 0)
        mark = "  " if count else "  <- never produced"
        print(f"  {action:<22} {count}{mark}")

    print()
    print("GATE VERDICTS")
    for reason, count in gates.most_common():
        print(f"  {reason:<22} {count}")

    unseen = [a for a in ACTION_TYPES if a != "no_action" and not actions.get(a)]
    if unseen:
        print()
        print(f"  {len(unseen)} of 8 actions were not produced by any row above: "
              f"{', '.join(unseen)}.")
        print("  That is a finding about the ladder or the strategist, not about this script.")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skill", default="intermediate",
        choices=["low", "beginner", "intermediate", "advanced"],
        help="Learner skill level in the prompt.",
    )
    parser.add_argument(
        "--withhold", type=float, default=0.0,
        help="Trial withhold rate. Defaults to 0 so every eligible row is visible; set it to "
             "0.35 to see the control arm the deployment actually runs.",
    )
    args = parser.parse_args()

    prime_config(withhold=args.withhold)
    config = config_service.get_config()

    print("=" * 92)
    print(f"endpoint     : {settings.VLLM_ENDPOINT.rstrip('/')}/v1")
    print(f"model        : {settings.VLLM_MODEL}")
    print(f"timeout      : {settings.VLLM_TIMEOUT_SECONDS}s")
    print(f"adapt_states : {', '.join(config.adapt_states)}   (run-only)")
    print(f"withhold     : {config.withhold_rate}")
    print(f"skill        : {args.skill}")
    print("=" * 92)
    for line in unreachable_note():
        print(f"\n  NOTE: {line}")
    print()

    rows = []
    # A distinct cycle number per row, so the cooldown marker the profiler stamps on one row never
    # withholds the next -- and so the withhold draw, which hashes the cycle, varies.
    for cycle, (affect, rung) in enumerate(GRID, start=1):
        row = await run_one(affect, rung, cycle * 10, args.skill)
        rows.append(row)
        print_row(row)

    print_summary(rows)


if __name__ == "__main__":
    asyncio.run(main())
