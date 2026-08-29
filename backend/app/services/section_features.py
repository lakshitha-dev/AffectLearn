"""Per-section confusion features, derived from research events the platform already records.

WHY THIS EXISTS

The deployed behavioural model (`behavioral_confusion_gbdt`) is structurally blind on this UI.
Four of its sixteen features are scroll-based, but the lesson page shows ONE SECTION PER PAGE with
next/prev navigation, so a learner barely scrolls. Measured live: 2 scroll events per 30s window and
`P(confused) = 0.008` while the user was deliberately trying to appear confused. Its own training
sidecar explains why — "DUX participants used business software, not learning material."

So this module works at a different granularity: the SECTION, not the 30-second window. That is the
unit a paginated lesson actually has, and — critically — the unit `self_report` labels attach to
(`payload.section_id`), which makes these features trainable against real learner labels later.

WHAT THIS IS NOT

This does NOT feed the live model. `feature_engineering.FEATURE_NAMES` is frozen at 16 by the
deployed ONNX artifact, and `behavioral_inference.py:276` raises on any width mismatch. Adding
features there would break inference. This ships DARK: features are computed and logged next to the
self-report label so a future model can be trained on them. Live predictions must be unchanged.

JOIN KEY

`learner_id` + `section_id` — NOT `session_id`. Section and quiz events are emitted from REST routes
with `session_id=None`, while `self_report` arrives over the WebSocket and carries one. Joining on
session id would match nothing.
"""

from __future__ import annotations

from typing import Any, Iterable

import structlog

logger = structlog.get_logger(__name__)

# Event types this module consumes. Kept explicit so an unrelated event type appearing in the
# stream can never silently change a feature value.
SECTION_COMPLETED = "section_completed"
SECTION_VIEWED = "section_viewed"
SECTION_BACK_NAV = "section_back_nav"
SHOW_ANSWER_REVEALED = "show_answer_revealed"
QUIZ_SUBMITTED = "quiz_submitted"
EXERCISE_ATTEMPTED = "exercise_attempted"
ADAPTATION_INTERACTION = "adaptation_interaction"

# Bump when the meaning or membership of FEATURE_NAMES changes, so an analyst can tell two
# vintages of logged rows apart. Independent of `feature_engineering.FEATURE_SCHEMA_VERSION`,
# which versions the LIVE model's input and must not be touched.
SECTION_FEATURE_SCHEMA_VERSION = 1

FEATURE_NAMES: tuple[str, ...] = (
    # engagement / dwell
    "time_on_section_s",
    "time_per_100_words",
    "view_count",
    "back_nav_count",
    # struggle
    "show_answer_used",
    "quiz_attempt_count",
    "quiz_incorrect_count",
    "quiz_response_time_ms_mean",
    "exercise_attempt_count",
    # help received
    "adaptation_delivered_count",
    "adaptation_dismissed_count",
    # section shape — context, not behaviour. Lets a model learn "long FOR THIS KIND of section"
    # instead of hand-crafting a ratio. `estimated_duration_minutes` is deliberately NOT used:
    # across the 49 authored sections it takes only 5 distinct values (44 are 4 or 5 minutes) and
    # does not track content at all — a 367-word section and a 71-word section are both "5 min".
    "n_words",
    "n_blocks",
    "n_code_blocks",
    "has_exercise",
    "has_quiz",
)


def _payload(event: Any) -> dict:
    """Event payload as a dict, whether the event is an ORM row or a plain dict. Never raises."""
    if isinstance(event, dict):
        p = event.get("payload")
    else:
        p = getattr(event, "payload", None)
    return p if isinstance(p, dict) else {}


def _event_type(event: Any) -> str:
    if isinstance(event, dict):
        return str(event.get("event_type") or "")
    return str(getattr(event, "event_type", "") or "")


def _matches_section(event: Any, section_id: str) -> bool:
    return str(_payload(event).get("section_id") or "") == section_id


def extract(
    events: Iterable[Any],
    section_id: str,
    section_shape: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive the feature row for one section from that learner's events. Pure; never raises.

    `events` may include events for other sections — they are filtered by `payload.section_id`.
    `section_shape` comes from `section_shape_from_blocks`; when absent the shape features are 0
    and `time_per_100_words` falls back to `time_on_section_s` (no normalisation) rather than
    dividing by zero.

    Every feature is numeric so the row can go straight into a model matrix later; booleans are
    emitted as 0/1 for the same reason.
    """
    rows = [e for e in events if _matches_section(e, section_id)]

    time_on_section_s = 0.0
    view_count = 0
    back_nav_count = 0
    show_answer_used = 0
    quiz_attempts = 0
    quiz_incorrect = 0
    quiz_times: list[float] = []
    exercise_attempts = 0
    adaptation_delivered = 0
    adaptation_dismissed = 0

    for e in rows:
        kind = _event_type(e)
        p = _payload(e)

        if kind == SECTION_COMPLETED:
            # `time_spent_seconds` is the learner-facing dwell measurement sent by the lesson page.
            # Take the MAX across completions: the route is idempotent and re-completion emits
            # again, so summing would double-count a section the learner merely revisited.
            try:
                time_on_section_s = max(time_on_section_s, float(p.get("time_spent_seconds") or 0))
            except (TypeError, ValueError):
                pass
        elif kind == SECTION_VIEWED:
            view_count += 1
            try:
                time_on_section_s = max(time_on_section_s, float(p.get("dwell_seconds") or 0))
            except (TypeError, ValueError):
                pass
        elif kind == SECTION_BACK_NAV:
            back_nav_count += 1
        elif kind == SHOW_ANSWER_REVEALED:
            show_answer_used = 1
        elif kind == QUIZ_SUBMITTED:
            quiz_attempts += 1
            if not p.get("is_correct"):
                quiz_incorrect += 1
            rt = p.get("response_time_ms")
            if isinstance(rt, (int, float)) and rt >= 0:
                quiz_times.append(float(rt))
        elif kind == EXERCISE_ATTEMPTED:
            exercise_attempts += 1
        elif kind == ADAPTATION_INTERACTION:
            adaptation_delivered += 1
            if p.get("interaction") == "dismissed":
                adaptation_dismissed += 1

    shape = section_shape or {}
    n_words = int(shape.get("n_words") or 0)

    # Normalise dwell by MEASURED content, not the authored estimate (see FEATURE_NAMES comment).
    # With no word count there is nothing to normalise by, so pass the raw dwell through rather
    # than inventing a denominator.
    time_per_100_words = (
        (time_on_section_s / n_words * 100.0) if n_words > 0 else time_on_section_s
    )

    return {
        "section_id": section_id,
        "schema_version": SECTION_FEATURE_SCHEMA_VERSION,
        "time_on_section_s": round(time_on_section_s, 3),
        "time_per_100_words": round(time_per_100_words, 3),
        "view_count": view_count,
        "back_nav_count": back_nav_count,
        "show_answer_used": show_answer_used,
        "quiz_attempt_count": quiz_attempts,
        "quiz_incorrect_count": quiz_incorrect,
        "quiz_response_time_ms_mean": (
            round(sum(quiz_times) / len(quiz_times), 1) if quiz_times else 0.0
        ),
        "exercise_attempt_count": exercise_attempts,
        "adaptation_delivered_count": adaptation_delivered,
        "adaptation_dismissed_count": adaptation_dismissed,
        "n_words": n_words,
        "n_blocks": int(shape.get("n_blocks") or 0),
        "n_code_blocks": int(shape.get("n_code_blocks") or 0),
        "has_exercise": int(bool(shape.get("has_exercise"))),
        "has_quiz": int(bool(shape.get("has_quiz"))),
    }


def from_signals(
    signals: dict[str, Any] | None,
    section_id: str,
    section_shape: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the same feature row from counters the CLIENT accumulated. Pure; never raises.

    This is the LIVE path, and it exists because `extract` cannot be used at completion time.
    `research_logger.emit` publishes to a Redis stream that a background worker later drains into
    Postgres, so the events for a section are not queryable when the learner completes it — and if
    Redis is down they never arrive. Reading them back would yield a silently empty row.

    The lesson page already holds every counter for the section it is leaving, so it sends them in
    the completion request: synchronous, durable in the request body, Redis-independent.

    `extract` remains the OFFLINE path (Phase 2 analysis over the landed event store). Both emit
    identical keys — `test_signal_and_event_paths_agree` pins that, so the two cannot drift.
    """
    s = signals or {}

    def _num(key: str, default: float = 0.0) -> float:
        v = s.get(key)
        if isinstance(v, bool):
            return float(v)
        if isinstance(v, (int, float)):
            return float(v)
        return default

    time_on_section_s = max(0.0, _num("time_on_section_s"))
    shape = section_shape or {}
    n_words = int(shape.get("n_words") or 0)
    time_per_100_words = (
        (time_on_section_s / n_words * 100.0) if n_words > 0 else time_on_section_s
    )

    return {
        "section_id": section_id,
        "schema_version": SECTION_FEATURE_SCHEMA_VERSION,
        "time_on_section_s": round(time_on_section_s, 3),
        "time_per_100_words": round(time_per_100_words, 3),
        "view_count": int(_num("view_count")),
        "back_nav_count": int(_num("back_nav_count")),
        "show_answer_used": 1 if _num("show_answer_used") > 0 else 0,
        "quiz_attempt_count": int(_num("quiz_attempt_count")),
        "quiz_incorrect_count": int(_num("quiz_incorrect_count")),
        "quiz_response_time_ms_mean": round(_num("quiz_response_time_ms_mean"), 1),
        "exercise_attempt_count": int(_num("exercise_attempt_count")),
        "adaptation_delivered_count": int(_num("adaptation_delivered_count")),
        "adaptation_dismissed_count": int(_num("adaptation_dismissed_count")),
        "n_words": n_words,
        "n_blocks": int(shape.get("n_blocks") or 0),
        "n_code_blocks": int(shape.get("n_code_blocks") or 0),
        "has_exercise": int(bool(shape.get("has_exercise"))),
        "has_quiz": int(bool(shape.get("has_quiz"))),
    }


def section_shape_from_blocks(blocks: Iterable[Any]) -> dict[str, Any]:
    """Content-shape descriptors for a section's blocks. Pure; never raises.

    Word count comes from the same rendering the LLM prompt uses
    (`content_context_service._render_body`), so "how much text is on this page" means one thing
    across the whole system rather than drifting between two definitions.
    """
    from app.services import content_context_service as ccs

    blocks = list(blocks or [])
    try:
        body = ccs._render_body(blocks)
    except Exception:  # noqa: BLE001 — shape is context, never worth failing a request over
        logger.warning("section_shape_render_failed", exc_info=True)
        body = ""

    kinds = []
    for b in blocks:
        bt = getattr(b, "block_type", None)
        kinds.append(str(getattr(bt, "value", bt) or ""))

    return {
        "n_words": len(body.split()),
        "n_blocks": len(blocks),
        "n_code_blocks": sum(1 for k in kinds if k == "code"),
        "has_exercise": any(k == "exercise" for k in kinds),
        "has_quiz": any(k == "quiz" for k in kinds),
    }
