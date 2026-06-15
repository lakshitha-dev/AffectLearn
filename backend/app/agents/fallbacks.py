"""Rule-based agent fallbacks (Story 5.1; placeholder added in Story 4.4).

When vLLM is slow, unavailable, or returns an unusable response, the pedagogical
strategist must STILL produce a valid strategy so the Phase B cycle completes (NFR22;
architecture line 632 — "If vLLM doesn't respond in 3s → use rule-based hint"). These
functions are PURE (no I/O) and deterministic, so they are unit-testable without an LLM
and give the loop a predictable safety net.

The mapping is intentionally conservative — one clear action per affect category
(epics 5.1 lines 911-929):

    confused   -> show_hint   (offer a gentler explanation)
    frustrated -> simplify    (reduce load; Content Adapter pairs encouragement)
    bored      -> skip_ahead  (re-engage by moving past familiar material)
    engaged    -> no_action   (don't interrupt a working flow)
    unknown    -> no_action   (safe default)

The richer, context-sensitive choices (alternative vs breakdown, increase_difficulty,
suggest_break for extended frustration) are the LLM's job; the fallback stays simple.
"""

from __future__ import annotations

from typing import Any

# Locked strategy vocabulary — the single source of truth for valid `action_type` values
# produced by the strategist (LLM or fallback). The node rejects anything outside this set.
ACTION_TYPES: tuple[str, ...] = (
    "no_action",
    "show_hint",
    "show_alternative",
    "show_breakdown",
    "show_encouragement",
    "simplify",
    "suggest_break",
    "skip_ahead",
    "increase_difficulty",
)

URGENCIES: tuple[str, ...] = ("low", "medium", "high")

# affect_state -> (action_type, urgency). Every value is in ACTION_TYPES / URGENCIES.
_RULE_MAP: dict[str, tuple[str, str]] = {
    "confused": ("show_hint", "medium"),
    "frustrated": ("simplify", "high"),
    "bored": ("skip_ahead", "low"),
    "engaged": ("no_action", "low"),
}


def rule_based_strategy(affect_state: Any, profile: dict | None = None) -> dict[str, Any]:
    """Deterministic strategy for an affect category. Pure; never raises.

    `profile` is accepted for signature parity with the LLM path (and future
    profile-aware rules) but the baseline mapping ignores it. An unknown or missing
    affect maps to `no_action` so the fallback is always safe.
    """
    action_type, urgency = _RULE_MAP.get(affect_state, ("no_action", "low"))
    return {
        "action_type": action_type,
        "reason": f"rule-based response to {affect_state or 'unknown'} affect",
        "urgency": urgency,
    }
