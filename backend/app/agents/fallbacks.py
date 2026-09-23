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
    # Added after the fine-tuned adapter was trained and evaluated on the nine actions above, so
    # only the served strategist uses it. The Pedagogical agent picks it; its Video sub-agent
    # (`nodes/video_resource.py`) finds the video.
    "show_video",
)

URGENCIES: tuple[str, ...] = ("low", "medium", "high")

# affect_state -> ESCALATION LADDER of (action_type, urgency), tried in order.
#
# WHY A LADDER AND NOT A SINGLE ACTION.
#
# This map used to be one action per state, so a learner confused three times in the same section
# received `show_hint` three times. Repeating an intervention that has already failed is not an
# adaptive system; it is a stuck one, and it makes "was the intervention adaptive?" unanswerable
# because nothing ever varied.
#
# The rungs are ORDERED BY COST TO THE LEARNER, cheapest first: a hint asks them to think again,
# a breakdown does some of the thinking for them, an alternative explanation replaces the framing
# they already have. Starting at the expensive end would resolve confusion that would have
# resolved on its own -- and confusion that resolves on its own is the kind that teaches
# (D'Mello et al. 2014), so spending it cheaply is a real loss.
#
# DETERMINISTIC AND FIXED, deliberately. A bandit would need thousands of events to learn an
# ordering; this study will have hundreds. A pre-registered ladder is auditable, reproducible from
# the record, and can be defended in a viva -- which a learned policy at this sample size cannot.
_RULE_LADDER: dict[str, tuple[tuple[str, str], ...]] = {
    # Cheapest nudge first, then structure, then a different framing altogether.
    # A video is the last rung: a different MEDIUM once three pieces of text have not landed,
    # and the most expensive for the learner (minutes of watching), so it comes after them.
    "confused": (("show_hint", "medium"), ("show_breakdown", "medium"),
                 ("show_alternative", "high"), ("show_video", "high")),
    # Flow theory places boredom at challenge BELOW skill, so raise challenge before conceding
    # that the material is not worth their time.
    "bored": (("increase_difficulty", "low"), ("skip_ahead", "medium")),
    # Frustration is the one state where withdrawal is a legitimate final rung.
    "frustrated": (("show_encouragement", "medium"), ("simplify", "high"),
                   ("suggest_break", "high")),
    "engaged": (("no_action", "low"),),
}


def ladder_for(affect_state: Any, rung: int = 0) -> tuple[str, str]:
    """The action at `rung` of this state's ladder, clamped to the last rung.

    Clamped rather than wrapping: once the deepest intervention has been tried, repeating it is
    the least-bad option left. Cycling back to a hint the learner has already dismissed would be
    actively worse, and there is no rung beyond "a different explanation" that this system can
    deliver.
    """
    rungs = _RULE_LADDER.get(affect_state)
    if not rungs:
        return ("no_action", "low")
    return rungs[min(max(0, int(rung or 0)), len(rungs) - 1)]


def rule_based_strategy(
    affect_state: Any, profile: dict | None = None, rung: int = 0
) -> dict[str, Any]:
    """Deterministic strategy for an affect category. Pure; never raises.

    `rung` is how many interventions this learner has already been DELIVERED for this state in
    this section — so a repeat escalates instead of repeating. `profile` is accepted for signature
    parity with the LLM path. An unknown or missing affect maps to `no_action`.
    """
    action_type, urgency = ladder_for(affect_state, rung)
    return {
        "action_type": action_type,
        "reason": f"rule-based response to {affect_state or 'unknown'} affect",
        "urgency": urgency,
    }


# ── Content Adapter partition + pre-written copy (Story 5.2) ───────────────────
#
# The Content Adapter (Agent 4) splits the locked ACTION_TYPES into two execution
# paths plus a no-op (epics 942-952):
#   - GENERATIVE_ACTIONS  -> call vLLM to produce warm, conversational learner-facing
#                            text. When vLLM is slow/absent/unusable the node falls
#                            back to the pre-written copy below (NFR22, NFR5).
#   - SELECTIVE_ACTIONS   -> do NOT generate prose; SELECT an existing content variant
#                            by reference, emitting a *selection descriptor*
#                            (`metadata.select`) a catalog lookup resolves.
#
# `increase_difficulty` MOVED from selective to generative (2026-09). It was the only
# response to boredom that raises challenge, and it delivered NOTHING: its descriptor
# pointed at a `challenge_exercise` catalog that does not exist -- no table, no resolver,
# no difficulty column on any content model -- so the client rendered null and the learner
# saw an empty box. Flow theory puts boredom at challenge BELOW skill, which makes raising
# challenge the theoretically correct response and not one worth leaving unimplemented.
# Generating a question from the section body needs no catalog: the Content Adapter is
# already given that body, so the challenge can be written against the real material.
#   - no_action           -> neither; produces NO content (the cycle ends cleanly).
GENERATIVE_ACTIONS: tuple[str, ...] = (
    "show_hint",
    "show_alternative",
    "show_breakdown",
    "show_encouragement",
    "suggest_break",
    "simplify",
    "increase_difficulty",
    # Generative for its one-line introduction; the video itself comes from the Video sub-agent.
    "show_video",
)
SELECTIVE_ACTIONS: tuple[str, ...] = ("skip_ahead",)

# Module-level invariant: every action is classified exactly once, except `no_action`
# which is deliberately in neither set (it produces no content). This keeps the
# partition a true single source of truth and fails loudly if ACTION_TYPES drifts.
assert set(GENERATIVE_ACTIONS) | set(SELECTIVE_ACTIONS) | {"no_action"} == set(ACTION_TYPES)
assert not (set(GENERATIVE_ACTIONS) & set(SELECTIVE_ACTIONS))

# Pre-written, warm/conversational fallback copy per generative action (epics 948 —
# tone is NEVER clinical: "Here's another way to think about this...", not "Difficulty
# reduced"). Used verbatim when vLLM cannot be reached or returns nothing usable.
_GENERATIVE_COPY: dict[str, str] = {
    "show_hint": (
        "Here's another way to think about this: try connecting it to something you "
        "already know well, and see if the pieces start to line up."
    ),
    "show_alternative": (
        "Let's look at this from a different angle. Sometimes the same idea makes a lot "
        "more sense when we approach it a new way — give this version a read and see if "
        "it clicks better for you."
    ),
    "show_breakdown": (
        "Let's take this one step at a time:\n"
        "1. Start with the core idea and make sure that part feels solid.\n"
        "2. Add the next piece, checking how it connects to the first.\n"
        "3. Put it together and try a quick example to see it in action."
    ),
    "show_encouragement": (
        "You're doing great — sticking with the tricky parts is exactly how this starts "
        "to click. Keep going!"
    ),
    "suggest_break": (
        "You've been working hard for a while. How about a short break to stretch and "
        "rest your eyes? A few minutes away can make the next part feel much easier."
    ),
    "simplify": (
        "Let's slow down and take this more gently. Here's the same idea in simpler "
        "terms — no rush, we'll build it back up once this part feels comfortable."
    ),
    # Deliberately a QUESTION, not an announcement. The point of this action is to raise
    # challenge, so the fallback has to ask the learner to do something -- "here is a harder
    # thing" with no harder thing attached is exactly the empty gesture this action used to be.
    "show_video": (
        "Sometimes it helps to watch someone work through it. Here's a short video on exactly "
        "this idea."
    ),
    "increase_difficulty": (
        "Ready for something with a bit more bite? Try this: without scrolling back, explain "
        "in your own words why this idea works the way it does — and where it would break down."
    ),
}

# Selection descriptors for selective actions: what an existing-variant lookup should
# fetch (`metadata.select`), plus a brief warm framing line (no generated prose).
_SELECTIVE_COPY: dict[str, tuple[str, str]] = {
    # action_type -> (brief framing text, select target)
    "skip_ahead": (
        "You've got a good handle on this — let's move ahead to something new.",
        "next_section",
    ),
}


def rule_based_content(action_type: Any, context: dict | None = None) -> dict[str, Any]:
    """Deterministic learner-facing content for an action. Pure; never raises.

    Returns a well-formed ``{text, variant, metadata}`` dict for every input:

    * Generative action -> pre-written warm/conversational ``text`` (the fallback when
      vLLM is unavailable), ``variant`` == the action type, ``metadata.action_type``.
    * Selective action  -> a brief framing ``text`` plus a *selection descriptor*
      (``metadata.select``); no prose is required to satisfy the action.
    * ``no_action`` or any unknown/junk input -> a safe empty descriptor
      (``variant="no_action"``, empty ``text``) so the caller can detect "no content".

    ``context`` is accepted for signature parity with the LLM path (and so future
    rules can ground the copy in topic/difficulty); the baseline copy ignores it.
    The function performs NO I/O and never raises, so it is the loop's safety net.
    """
    if isinstance(action_type, str) and action_type in _GENERATIVE_COPY:
        return {
            "text": _GENERATIVE_COPY[action_type],
            "variant": action_type,
            "metadata": {"action_type": action_type},
        }
    if isinstance(action_type, str) and action_type in _SELECTIVE_COPY:
        text, select = _SELECTIVE_COPY[action_type]
        return {
            "text": text,
            "variant": action_type,
            "metadata": {"action_type": action_type, "select": select},
        }
    # no_action or anything out of vocabulary -> safe empty result (no intervention).
    return {
        "text": "",
        "variant": "no_action",
        "metadata": {"action_type": "no_action"},
    }


def ladder_actions(affect_state: Any) -> tuple[str, ...]:
    """The escalation order for a state, as action names.

    Exposed so the strategist's PROMPT can show the model the same ladder the deterministic
    fallback walks. Restating it in the prompt text would let the two drift, and the drift would
    be silent: the model would be told one escalation order while the fallback used another, and
    the difference only shows up as an odd intervention six rungs into a session.
    """
    return tuple(action for action, _urgency in _RULE_LADDER.get(affect_state, ()))
