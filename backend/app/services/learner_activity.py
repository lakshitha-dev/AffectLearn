"""What the learner has DONE in the section they are on, for the two agents that write to them.

WHY THIS EXISTS

The client already reports struggle counters for the current section -- wrong answers, revealing
an answer, going back to re-read, time spent -- on the `performance_window` message. They fed the
performance channel's score and nothing else. The strategist and the content adapter never saw
them, so a hint written for a learner who had just answered the section's question wrong three
times read exactly like one written for a learner who had not tried it yet. A tutor who can see
the wrong answers and ignores them is not adapting.

The performance window is a separate message from the facial and behavioural cycles, so the
latest counters are kept here, keyed by learner and section, and attached to whichever cycle
next reaches the agents.

WHAT THIS IS NOT

Not a detection channel and not a gate input. It changes what the agents SAY once the gate has
already decided to act, never WHETHER they act -- so it cannot move any gate rate the thesis
reports. Best-effort throughout: a Redis outage costs the context, never the cycle (NFR22).
"""

from __future__ import annotations

from typing import Any

import structlog

from app.services import redis_service

logger = structlog.get_logger(__name__)

#: Long enough to span a learner working through one section, short enough that counters from a
#: section visited this morning do not colour a hint this afternoon.
_TTL_SECONDS = 30 * 60

#: The counters kept. Anything else the client sends is ignored, so a new client field cannot
#: reach a prompt without being named here first.
_FIELDS = ("quiz_incorrect_count", "back_nav_count", "show_answer_used", "time_on_section_s")


def _key(learner_id: Any, section_id: Any) -> str:
    return f"activity:{learner_id}:{section_id}"


def _clean(counts: Any) -> dict[str, Any]:
    """Keep the known fields, coerced to safe types. Pure; never raises."""
    data = counts if isinstance(counts, dict) else {}
    out: dict[str, Any] = {}
    for field in ("quiz_incorrect_count", "back_nav_count"):
        try:
            out[field] = max(0, int(data.get(field) or 0))
        except (TypeError, ValueError):
            out[field] = 0
    out["show_answer_used"] = bool(data.get("show_answer_used"))
    try:
        out["time_on_section_s"] = max(0.0, round(float(data.get("time_on_section_s") or 0), 1))
    except (TypeError, ValueError):
        out["time_on_section_s"] = 0.0
    return out


async def record(learner_id: Any, section_id: Any, counts: Any) -> None:
    """Store the latest counters for this learner and section. Never raises."""
    if not learner_id or not section_id:
        return
    try:
        await redis_service.set_json(
            _key(learner_id, section_id), _clean(counts), ttl_seconds=_TTL_SECONDS
        )
    except Exception:  # noqa: BLE001 -- context is optional; the cycle is not
        logger.warning("learner_activity_record_failed", exc_info=True)


async def get(learner_id: Any, section_id: Any) -> dict[str, Any] | None:
    """The latest counters for this learner and section, or None. Never raises."""
    if not learner_id or not section_id:
        return None
    try:
        value = await redis_service.get_json(_key(learner_id, section_id))
    except Exception:  # noqa: BLE001
        logger.warning("learner_activity_get_failed", exc_info=True)
        return None
    return _clean(value) if isinstance(value, dict) else None


async def attach(content_context: dict[str, Any] | None, learner_id: Any) -> dict[str, Any]:
    """Return a COPY of `content_context` carrying this learner's activity for its section.

    A copy, never a mutation: `content_context_service.build` returns a dict from a cache shared by
    every learner on the section, so writing one learner's counters into it would hand them to the
    next learner's prompt.
    """
    context = dict(content_context or {})
    activity = await get(learner_id, context.get("section_id"))
    if activity:
        context["learner_activity"] = activity
    return context


def describe(activity: Any) -> str:
    """One plain-English line for a prompt, or "" when there is nothing worth saying. Pure.

    Only what was observed is stated, in counts, with no interpretation: whether two wrong answers
    mean a misconception is the model's judgement to make, and it can only make it if the line
    does not make it first.
    """
    data = _clean(activity) if isinstance(activity, dict) else None
    if not data:
        return ""
    parts: list[str] = []
    wrong = data["quiz_incorrect_count"]
    if wrong:
        parts.append(f"answered this section's question incorrectly {wrong} time(s)")
    if data["show_answer_used"]:
        parts.append("revealed the answer instead of working it out")
    back = data["back_nav_count"]
    if back:
        parts.append(f"went back to re-read {back} time(s)")
    seconds = data["time_on_section_s"]
    if seconds >= 60:
        parts.append(f"has spent about {round(seconds / 60)} minute(s) on this section")
    return "; ".join(parts)
