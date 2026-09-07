"""Self-report label quality (Story 8.6 / FR48).

The self-report widget is the pilot's ground-truth label source: everything the behavioural model
is validated against is a learner saying how they felt. Every prompt and every response has been
recorded as a `self_report` research event since Story 6.2 — and nothing read them back to ask
whether the labels are any good.

That question is not optional for a study whose headline result rests on those labels. A
participant who answers "engaged" to every prompt because it is the first button produces a
perfectly clean-looking dataset that measures nothing, and the only way to notice is to look at
the distribution.

WHAT IS AND IS NOT A JUDGEMENT

The counts and rates here are facts. The fatigue flag is a HEURISTIC and is reported as one: a
session whose labels are almost all identical MIGHT be an honest reflection of a consistent
session, or might be someone clicking through. This service says which sessions look like the
latter; it does not exclude them, and there is deliberately no endpoint that does. Deciding what
to drop from an analysis is the researcher's call and belongs in the analysis, where it can be
written down and defended, not in a hidden flag on an admin screen.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_event import ResearchEvent

SELF_REPORT = "self_report"

#: Below this many answered prompts a session's distribution says nothing — three identical
#: answers out of three is not evidence of fatigue, it is a short session.
_MIN_ANSWERS_FOR_FATIGUE = 5

#: At or above this share on a single affect, a session is flagged for review.
_DOMINANT_SHARE = 0.9


def _payload_of(event: ResearchEvent) -> dict[str, Any]:
    return event.payload or {}


def _is_skipped(payload: dict[str, Any]) -> bool:
    """A prompt the learner was shown and declined.

    `skipped` and `omitted` are distinct in the wire payload and both mean "no label", so both
    count against the answer rate — but only `skipped` is a learner ACTION.
    """
    return bool(payload.get("skipped")) or bool(payload.get("omitted"))


async def summary(db: AsyncSession) -> dict[str, Any]:
    """Overall label distribution, answer/skip rates, and per-session quality."""
    events = (
        await db.execute(
            select(ResearchEvent)
            .where(ResearchEvent.event_type == SELF_REPORT)
            .order_by(ResearchEvent.timestamp.asc())
        )
    ).scalars().all()

    distribution: dict[str, int] = defaultdict(int)
    per_session: dict[str, dict[str, Any]] = {}
    total_prompts = 0
    total_skipped = 0

    for event in events:
        payload = _payload_of(event)
        session_id = event.session_id or "unknown"
        session = per_session.setdefault(
            session_id,
            {
                "session_id": session_id,
                "learner_id": event.learner_id,
                "prompts": 0,
                "skipped": 0,
                "distribution": defaultdict(int),
            },
        )

        total_prompts += 1
        session["prompts"] += 1

        if _is_skipped(payload):
            total_skipped += 1
            session["skipped"] += 1
            continue

        affect = payload.get("affect")
        if not affect:
            continue
        distribution[str(affect)] += 1
        session["distribution"][str(affect)] += 1

    answered = total_prompts - total_skipped

    sessions = []
    for session in per_session.values():
        session_answered = session["prompts"] - session["skipped"]
        counts = dict(session["distribution"])
        dominant_affect, dominant_count = (
            max(counts.items(), key=lambda kv: kv[1]) if counts else (None, 0)
        )
        dominant_share = (dominant_count / session_answered) if session_answered else None

        # The heuristic, stated rather than hidden. Both conditions are required: a short session
        # cannot be distinguished from a consistent one, so it is not flagged either way.
        fatigue = bool(
            session_answered >= _MIN_ANSWERS_FOR_FATIGUE
            and dominant_share is not None
            and dominant_share >= _DOMINANT_SHARE
        )

        sessions.append(
            {
                "session_id": session["session_id"],
                "learner_id": session["learner_id"],
                "prompts": session["prompts"],
                "answered": session_answered,
                "skipped": session["skipped"],
                "skip_rate": (session["skipped"] / session["prompts"])
                if session["prompts"]
                else None,
                "distinct_labels": len(counts),
                "dominant_affect": dominant_affect,
                "dominant_share": dominant_share,
                "low_variance": fatigue,
                "distribution": counts,
            }
        )

    # Worst first: the sessions a researcher needs to look at, not the ones that are fine.
    sessions.sort(key=lambda s: (not s["low_variance"], -(s["skip_rate"] or 0)))

    return {
        "total_prompts": total_prompts,
        "answered": answered,
        "skipped": total_skipped,
        "skip_rate": (total_skipped / total_prompts) if total_prompts else None,
        "distribution": dict(distribution),
        "sessions": sessions,
        "flagged_sessions": sum(1 for s in sessions if s["low_variance"]),
        # Stated so the number on screen can be interpreted without reading this file.
        "fatigue_criteria": {
            "min_answers": _MIN_ANSWERS_FOR_FATIGUE,
            "dominant_share": _DOMINANT_SHARE,
        },
    }
