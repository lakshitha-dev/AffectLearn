"""What is on the learner's screen right now, and whether an automatic intervention may interrupt it.

WHY THIS EXISTS

The adaptation gate judges the DETECTOR: is the reading confident, sustained, and outside the
cooldown. It had no idea what the learner was looking at, and a learner experienced the gap:

  * a new card replaced the step-by-step they were halfway through reading, or the video they were
    two minutes into, because 90 seconds of cooldown is shorter than either;
  * reading a card at the bottom of the screen (eyes down) could itself read as disengagement and
    trigger a challenge card over the help;
  * a hint written for the section they had just LEFT arrived on the one they had moved to, because
    a 30-second window is sent when it closes, not when it started;
  * "Got it" and "not now" changed nothing -- the next, heavier rung came anyway;
  * at the top of the ladder the same video / skip-ahead offer repeated every 90 seconds;
  * a card could arrive into a hidden tab, or in the middle of answering a question.

This module is the learner-side half of the gate. It is PURE: `ui` is a small dict the WebSocket
handler keeps per learner (in Redis, `services/ui_state.py`) and feeds into each cycle's state.

WHAT IT DOES NOT TOUCH

Only DETECTOR-driven cycles are held. A learner who presses "Still stuck" or "I'd rather move on"
is asking, and a request bypasses all of this (`edges.adaptation_decision` returns before the
guard). The holds run before the randomised trial draw, so both arms see the same eligibility and
the trial stays matched; none of them spends the trial cooldown or the session cap.

An absent `ui` (an older client that sends no UI events) means no holds: exactly the behaviour
that existed before.
"""

from __future__ import annotations

from typing import Any

from app.agents import fallbacks

# ── withholding reasons (surfaced on the monitor like every other gate reason) ──────────
GATE_STALE_SECTION = "stale_section"      # the reading is about a section the learner has left
GATE_PAGE_HIDDEN = "page_hidden"          # the learner is on another tab / app
GATE_CARD_OPEN = "card_open"              # a help card (or its video) is still on screen
GATE_SECTION_GRACE = "section_grace"      # the learner has only just arrived on this section
GATE_QUIZ_ACTIVE = "quiz_active"          # the learner is answering a question
GATE_RECENT_HELP = "recent_help"          # help was delivered, or dismissed, moments ago
GATE_RESOLVED = "resolved"                # the learner said "Got it" for this, here, recently
GATE_LADDER_EXHAUSTED = "ladder_exhausted"  # every rung has been tried in this section

GUARD_REASONS: tuple[str, ...] = (
    GATE_STALE_SECTION,
    GATE_PAGE_HIDDEN,
    GATE_CARD_OPEN,
    GATE_SECTION_GRACE,
    GATE_QUIZ_ACTIVE,
    GATE_RECENT_HELP,
    GATE_RESOLVED,
    GATE_LADDER_EXHAUSTED,
)

# ── timings (ms) ────────────────────────────────────────────────────────────────────────
#: How long a text card counts as "being read" if the learner neither answers nor closes it.
TEXT_CARD_HOLD_MS = 3 * 60_000
#: A video card holds for its whole plausible length (videos are 2-15 minutes).
VIDEO_CARD_HOLD_MS = 20 * 60_000
#: No automatic help this soon after arriving on a section: the first window is about the last one.
SECTION_GRACE_MS = 45_000
#: No two automatic cards closer than this, whatever triggered the earlier one.
MIN_SPACING_MS = 60_000
#: "Not now": wait longer before offering again.
DISMISS_HOLD_MS = 150_000
#: "Got it": leave this state alone in this section for a while.
RESOLVED_HOLD_MS = 5 * 60_000
#: Answering a question: no interruption until shortly after the last interaction with it.
QUIZ_HOLD_MS = 45_000


def state_for_action(action: Any) -> str | None:
    """Which ladder an action belongs to ("confused" or "bored"), or None."""
    for state in ("confused", "bored", "frustrated"):
        if action in fallbacks.ladder_actions(state):
            return state
    return None


def _key(section_id: Any, affect_state: Any) -> str:
    return f"{section_id}:{affect_state}"


# ── the check ───────────────────────────────────────────────────────────────────────────


def blocked_reason(
    ui: dict[str, Any] | None,
    *,
    now_ms: int,
    section_id: Any,
    affect_state: Any,
    rungs_used: int,
) -> str | None:
    """Why an automatic intervention must not interrupt now, or None if it may. Pure; never raises."""
    if not isinstance(ui, dict) or not ui:
        return None

    current = ui.get("section_id")
    if current and section_id and str(section_id) != str(current):
        return GATE_STALE_SECTION
    if ui.get("page_hidden"):
        return GATE_PAGE_HIDDEN

    card = ui.get("open_card")
    if isinstance(card, dict) and now_ms < int(card.get("until_ms") or 0):
        return GATE_CARD_OPEN

    entered = int(ui.get("entered_ms") or 0)
    if entered and now_ms - entered < SECTION_GRACE_MS:
        return GATE_SECTION_GRACE
    if now_ms < int(ui.get("quiz_until_ms") or 0):
        return GATE_QUIZ_ACTIVE

    last = int(ui.get("last_delivery_ms") or 0)
    if (last and now_ms - last < MIN_SPACING_MS) or now_ms < int(ui.get("dismissed_until_ms") or 0):
        return GATE_RECENT_HELP

    resolved = ui.get("resolved") or {}
    if isinstance(resolved, dict) and now_ms < int(resolved.get(_key(section_id, affect_state)) or 0):
        return GATE_RESOLVED

    ladder = fallbacks.ladder_actions(affect_state)
    if ladder and rungs_used >= len(ladder):
        return GATE_LADDER_EXHAUSTED
    return None


def rung_credit(ui: dict[str, Any] | None, section_id: Any, affect_state: Any) -> int:
    """Deliveries the learner dismissed here: they were "not now", not "that did not help"."""
    if not isinstance(ui, dict):
        return 0
    credit = ui.get("rung_credit") or {}
    try:
        return max(0, int(credit.get(_key(section_id, affect_state)) or 0))
    except (TypeError, ValueError, AttributeError):
        return 0


# ── updates (each returns a NEW dict) ───────────────────────────────────────────────────


def on_section_entered(ui: dict[str, Any], section_id: Any, now_ms: int) -> dict[str, Any]:
    """The learner is now on `section_id`. Anything on screen belonged to the previous one."""
    u = dict(ui or {})
    if not section_id or str(section_id) == str(u.get("section_id") or ""):
        return u
    u["section_id"] = str(section_id)
    u["entered_ms"] = now_ms
    u["open_card"] = None
    u["quiz_until_ms"] = 0
    return u


def on_visibility(ui: dict[str, Any], visible: bool) -> dict[str, Any]:
    u = dict(ui or {})
    u["page_hidden"] = not visible
    return u


def on_quiz_activity(ui: dict[str, Any], now_ms: int) -> dict[str, Any]:
    u = dict(ui or {})
    u["quiz_until_ms"] = now_ms + QUIZ_HOLD_MS
    return u


def on_video(ui: dict[str, Any], *, opened: bool, adaptation_id: Any, now_ms: int) -> dict[str, Any]:
    """A video started or stopped inside a card: while it plays, nothing replaces it."""
    u = dict(ui or {})
    if opened:
        u["open_card"] = {
            "adaptation_id": adaptation_id,
            "video": True,
            "until_ms": now_ms + VIDEO_CARD_HOLD_MS,
        }
    else:
        card = u.get("open_card")
        if isinstance(card, dict) and card.get("video"):
            u["open_card"] = None
    return u


def on_delivery(
    ui: dict[str, Any], *, adaptation_id: Any, action: Any, section_id: Any, now_ms: int
) -> dict[str, Any]:
    """A card has just been sent: it is on screen until answered, closed or timed out."""
    u = dict(ui or {})
    video = action == "show_video"
    u["last_delivery_ms"] = now_ms
    u["open_card"] = {
        "adaptation_id": adaptation_id,
        "action": action,
        "section_id": str(section_id) if section_id else None,
        "video": video,
        "until_ms": now_ms + (VIDEO_CARD_HOLD_MS if video else TEXT_CARD_HOLD_MS),
    }
    return u


def on_interaction(
    ui: dict[str, Any],
    *,
    interaction: str,
    action: Any,
    section_id: Any,
    now_ms: int,
) -> dict[str, Any]:
    """The learner answered a card: "Got it" (accepted), "not now" (dismissed), or asked for more."""
    u = dict(ui or {})
    u["open_card"] = None
    state = state_for_action(action)
    section = section_id or u.get("section_id")
    if interaction == "accepted" and state and section:
        resolved = dict(u.get("resolved") or {})
        resolved[_key(section, state)] = now_ms + RESOLVED_HOLD_MS
        u["resolved"] = resolved
    elif interaction == "dismissed":
        u["dismissed_until_ms"] = now_ms + DISMISS_HOLD_MS
        if state and section:
            credit = dict(u.get("rung_credit") or {})
            credit[_key(section, state)] = int(credit.get(_key(section, state)) or 0) + 1
            u["rung_credit"] = credit
    return u
