"""Pedagogical Strategist node (Story 5.1 — real logic; was a stub in Story 4.4).

Agent 3 of the loop, and the FIRST node to call the fine-tuned LLM. On the Phase B /
adaptive branch, after the profiler, it decides the intervention strategy from the
learner's affect, profile, and content context by calling Llama 3 8B via vLLM
(`langchain-openai`, OpenAI-compatible API). It writes a structured `strategy`
(`action_type`, `reason`, `urgency`) into `AgentState` for the Content Adapter (Story 5.2).

Resilience (NFR22; architecture line 632): unlike `affect_detection_node` (whose errors
propagate to the WS boundary), this node CATCHES its own LLM failures — timeout, error,
or an unparseable / out-of-vocabulary response — and falls back to the deterministic
`fallbacks.rule_based_strategy`, tagging the result `fallback=True` with a
`fallback_reason`. It NEVER raises, so a Phase B cycle always yields a decision. Every
decision (LLM or fallback) is emitted as a `strategy_decided` research event.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents import fallbacks
from app.agents.llm import get_chat_client
from app.agents.state import AFFECT_SOURCE_LEARNER_REQUEST, AFFECT_STATES, AgentState
from app.core.config import settings
from app.services import learner_activity
from app.services.research_logger import content_coords
from app.services.research_logger import emit as emit_research_event

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are the Pedagogical Strategist for an adaptive e-learning platform. Given a "
    "learner's current affective state, their profile, and the content they are studying, "
    "decide the single best teaching intervention.\n\n"
    "Reply with ONLY a JSON object: "
    '{"action_type": <action>, "reason": <short string>, "urgency": "low"|"medium"|"high"}.\n'
    "When action_type is show_video, ALSO include "
    '"video_brief": {"concept": <the exact idea the learner is stuck on, 3-6 words>, '
    '"query": <a 4-10 word YouTube search query for a beginner explanation of it>}. '
    "Your Video sub-agent uses this brief to find the video, so base it on what the learner "
    "got wrong, not only on the section title.\n"
    f"action_type MUST be one of: {', '.join(fallbacks.ACTION_TYPES)}.\n\n"
    "Guidance:\n"
    "- confused: show_hint (first/mild), then show_breakdown, then show_alternative as "
    "confusion persists, then show_video (a short video walkthrough) once text has not landed. "
    "Choose show_video EARLIER only on strong evidence: learner_activity shows 3 or more wrong "
    "answers, or learner_requested is yes after text help was already given.\n"
    "- frustrated: show_encouragement or simplify (moderate); suggest_break "
    "(high/extended, especially late sessions).\n"
    "- bored: increase_difficulty FIRST to re-engage. Only use skip_ahead once a harder "
    "version has already been tried and the learner is still bored.\n"
    "- engaged: no_action, or increase_difficulty only if engagement is sustained.\n"
    "\n"
    "ESCALATION: `interventions_already_delivered` says how many times you have ALREADY "
    "helped this learner, in this section, for this state. When it is above 0, do NOT "
    "repeat an intervention that has already been given - move to the next, more "
    "substantial rung of the ladder shown. Re-sending something the learner has already "
    "seen and not benefited from wastes the interruption.\n\n"
    "Use the learner profile (skill level, mastery, recent affect history) and content "
    "difficulty to choose. Prefer no_action over an unhelpful interruption.\n\n"
    "EVIDENCE: `learner_activity`, when present, is what the learner actually DID in this "
    "section. Repeated wrong answers or a revealed answer point to a misconception rather than "
    "a momentary lapse, so a nudge is usually too little; a learner who has not attempted "
    "anything yet usually needs only the nudge. Let that evidence, and `section_excerpt`, "
    "shape both the action and the reason."
)


def _ladder_hint(affect_state: str) -> str:
    """The escalation order for this state, as a readable arrow chain.

    Read from `fallbacks._RULE_LADDER` rather than restated here, so the guidance the model
    is given and the deterministic fallback can never describe different ladders.
    """
    rungs = fallbacks.ladder_actions(affect_state)
    return " -> ".join(rungs) if rungs else "no escalation defined"


#: How much of the section the strategist sees. Enough to know what the section is ABOUT, which a
#: title alone does not say; far short of the full body the content adapter gets, because this
#: node classifies into nine actions and the rest would only cost latency.
_EXCERPT_CHARS = 400


def _excerpt(body: Any) -> str:
    """The section's opening, cut at a word boundary and flattened to one line. Pure."""
    text = " ".join(str(body or "").split())
    if len(text) <= _EXCERPT_CHARS:
        return text
    cut = text[:_EXCERPT_CHARS].rsplit(" ", 1)[0]
    return f"{cut} ..."


def _build_human_prompt(
    affect_state: str,
    affect_confidence: Any,
    profile: dict,
    content_context: dict,
    rung: int = 0,
    requested: bool = False,
) -> str:
    """Compact, token-efficient context block for the LLM.

    Carries a short excerpt of the section rather than the whole body, unlike
    `content_adapter._build_human_prompt`. The strategist only picks an `action_type` from a
    locked vocabulary, and the full ~2000-char body would roughly double the prompt for every
    cycle. A title alone, though, left it unable to tell a definitional section from a worked
    exercise -- the difference between a hint and a breakdown -- so it gets the opening of the
    section, plus what the learner has actually done in it.
    """
    topic = content_context.get("topic", "unknown")
    difficulty = content_context.get("difficulty", "unknown")
    lesson = content_context.get("lesson")
    recent = (profile.get("affect_history") or [])[-5:]
    lesson_line = f"content_lesson: {lesson}\n" if lesson and lesson != "unknown" else ""
    excerpt = _excerpt(content_context.get("body"))
    excerpt_line = f"section_excerpt: {excerpt}\n" if excerpt else ""
    activity = learner_activity.describe(content_context.get("learner_activity"))
    activity_line = f"learner_activity: {activity}\n" if activity else ""
    # The learner pressed "Still stuck" / "I'd rather move on" on the card already shown.
    requested_line = (
        "learner_requested: yes, the learner explicitly asked for the next step\n"
        if requested else ""
    )
    return (
        f"affect_state: {affect_state}\n"
        f"affect_confidence: {affect_confidence}\n"
        f"skill_level: {profile.get('skill_level', 'unknown')}\n"
        f"topic_mastery: {profile.get('topic_mastery', {}).get(topic, 'unknown')}\n"
        f"format_preferences: {profile.get('format_preferences', {})}\n"
        f"recent_affect_history: {recent}\n"
        f"{lesson_line}"
        f"content_topic: {topic}\n"
        f"content_difficulty: {difficulty}\n"
        f"{excerpt_line}"
        f"{activity_line}"
        f"{requested_line}"
        # THE ESCALATION INPUTS. `rung` was a parameter of this function and was never
        # written into the prompt, so the model had no idea what had already been tried and
        # re-sent an identical breakdown to a learner who had just failed to understand that
        # breakdown. The ladder is included alongside it because a count alone does not say
        # what the next rung IS.
        f"interventions_already_delivered: {rung}\n"
        f"escalation_ladder: {_ladder_hint(affect_state)}"
    )


def _content_text(content: Any) -> str:
    """Normalise a chat message's content to a string (str or list-of-blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # content blocks (newer langchain)
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(content or "")


def _parse_strategy(text: str) -> dict[str, Any] | None:
    """Extract and validate a strategy object from raw LLM text.

    Returns a clean `{action_type, reason, urgency}` dict, or None if the text is not
    valid JSON, lacks/has an out-of-vocabulary `action_type`. An unknown `urgency` is
    coerced to "medium" rather than rejected.
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    action_type = obj.get("action_type")
    if action_type not in fallbacks.ACTION_TYPES:
        return None
    urgency = obj.get("urgency")
    if urgency not in fallbacks.URGENCIES:
        urgency = "medium"
    parsed: dict[str, Any] = {
        "action_type": action_type,
        "reason": str(obj.get("reason", ""))[:300],
        "urgency": urgency,
    }
    # The delegation to the Video sub-agent. Optional: without it the sub-agent writes its own
    # query from the section, so a model that omits the brief costs precision, never the video.
    brief = obj.get("video_brief")
    if action_type == "show_video" and isinstance(brief, dict):
        concept = " ".join(str(brief.get("concept") or "").split())[:80]
        query = " ".join(str(brief.get("query") or "").split())[:120]
        if concept and query:
            parsed["video_brief"] = {"concept": concept, "query": query}
    return parsed


async def _decide(
    affect_state: str | None,
    affect_confidence: Any,
    profile: dict,
    content_context: dict,
    rung: int = 0,
    requested: bool = False,
) -> dict[str, Any]:
    """Produce a strategy dict (with `fallback`/`fallback_reason` provenance). Never raises."""
    # No usable affect this cycle (e.g. empty/face-less cycle that still routed here):
    # skip the LLM and take the safe no_action rule.
    if affect_state not in AFFECT_STATES:
        strat = fallbacks.rule_based_strategy(affect_state, profile, rung)
        return {**strat, "fallback": True, "fallback_reason": "no_affect"}

    try:
        client = get_chat_client()
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=_build_human_prompt(
                    affect_state, affect_confidence, profile, content_context, rung,
                    requested,
                )
            ),
        ]
        resp = await asyncio.wait_for(
            client.ainvoke(messages), timeout=settings.VLLM_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        logger.warning("pedagogical_vllm_timeout", affect_state=affect_state)
        strat = fallbacks.rule_based_strategy(affect_state, profile, rung)
        return {**strat, "fallback": True, "fallback_reason": "timeout"}
    except Exception as exc:  # noqa: BLE001 — degrade on any vLLM/client error (NFR22)
        logger.warning("pedagogical_vllm_error", affect_state=affect_state, error=str(exc))
        strat = fallbacks.rule_based_strategy(affect_state, profile, rung)
        return {**strat, "fallback": True, "fallback_reason": "vllm_error"}

    parsed = _parse_strategy(_content_text(getattr(resp, "content", resp)))
    if parsed is None:
        logger.warning("pedagogical_parse_error", affect_state=affect_state)
        strat = fallbacks.rule_based_strategy(affect_state, profile, rung)
        return {**strat, "fallback": True, "fallback_reason": "parse_error"}

    return {**parsed, "fallback": False}


def _enforce_escalation(
    strategy: dict[str, Any], affect_state: Any, rung: int
) -> dict[str, Any]:
    """Refuse an intervention this learner has already been given here, and advance instead.

    WHY THIS IS CODE AND NOT A PROMPT INSTRUCTION

    The prompt tells the model how many interventions have already been delivered and shows it
    the ladder. Measured against gpt-4o-mini that is not enough: asked four times in a row about
    a learner who was still confused after a hint AND a breakdown, it returned `show_breakdown`
    every time — re-sending the learner the exact explanation they had just failed to understand.
    Small models follow a positive instruction ("prefer X") far more reliably than a negative one
    ("do not repeat Y"), and no amount of rewording made it dependable.

    The no-repeat property is the whole reason the ladder exists, so it is enforced rather than
    requested. The model keeps its judgement everywhere it is not repeating itself: an override
    only fires when the chosen action is one the ladder has already spent for this state.

    AUDITABILITY

    An override is recorded on the strategy as `escalation_enforced`, and the model's original
    choice is kept in `model_action_type`. Decision fidelity is a measured quantity in this
    project (Section 4.4), so a decision the system changed must not be indistinguishable in the
    record from one the model made.
    """
    if rung <= 0:
        return strategy

    ladder = fallbacks.ladder_actions(affect_state)
    if not ladder:
        return strategy

    chosen = strategy.get("action_type")
    already_spent = ladder[:rung]
    if chosen not in already_spent:
        return strategy

    # Clamped: past the last rung there is nothing deeper to offer, and repeating the deepest
    # intervention is the least-bad option left — the same rule `fallbacks.ladder_for` applies.
    next_action = ladder[min(rung, len(ladder) - 1)]
    if next_action == chosen:
        return strategy

    logger.info(
        "escalation_enforced",
        affect_state=affect_state,
        rung=rung,
        model_action_type=chosen,
        enforced_action_type=next_action,
    )
    return {
        **strategy,
        "action_type": next_action,
        "escalation_enforced": True,
        "model_action_type": chosen,
    }


def _honour_request(
    strategy: dict[str, Any], state: AgentState, rung: int
) -> dict[str, Any]:
    """Never answer a learner's explicit request for help with `no_action`.

    `no_action` is the right call when a DETECTOR may be wrong: interrupting a coping learner
    costs more than a missed window. When the learner pressed "Still stuck" there is nothing to be
    wrong about, and replying with silence would read as the button being broken. The ladder's
    rung for this state stands in, recorded the same way `_enforce_escalation` records its
    overrides so a changed decision is never indistinguishable from the model's own.
    """
    if state.get("affect_source") != AFFECT_SOURCE_LEARNER_REQUEST:
        return strategy
    if strategy.get("action_type") != "no_action":
        return strategy
    action_type, urgency = fallbacks.ladder_for(state.get("affect_state"), rung)
    if action_type == "no_action":
        return strategy
    logger.info("learner_request_honoured", model_action_type="no_action", enforced=action_type)
    return {
        **strategy,
        "action_type": action_type,
        "urgency": urgency,
        "escalation_enforced": True,
        "model_action_type": "no_action",
    }


async def pedagogical_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: decide and write the intervention `strategy`. Never raises (NFR22)."""
    affect_state = state.get("affect_state")
    cycle = state.get("cycle_number")
    profile = state.get("learner_profile") or {}
    content_context = state.get("content_context") or {}

    # Computed by the profiler, which is the only node holding the fresh profile. It is how
    # many interventions were delivered to this learner, in this section, for this state
    # BEFORE this cycle -- so rung 0 really is the first one.
    rung = int(state.get("ladder_rung", 0) or 0)

    strategy = await _decide(
        affect_state,
        state.get("affect_confidence"),
        profile,
        content_context,
        rung,
        requested=state.get("affect_source") == AFFECT_SOURCE_LEARNER_REQUEST,
    )
    strategy = _enforce_escalation(strategy, affect_state, rung)
    strategy = _honour_request(strategy, state, rung)

    logger.info(
        "strategy_decided",
        learner_id=state.get("learner_id"),
        cycle=cycle,
        affect_state=affect_state,
        action_type=strategy["action_type"],
        fallback=strategy["fallback"],
    )
    await emit_research_event({
        "event_type": "strategy_decided",
        "learner_id": state.get("learner_id"),
        "session_id": state.get("session_id"),
        "cycle_number": cycle or 0,
        "timestamp": int(time.time() * 1000),
        # Story 6.5: top-level phase/group so the event is filterable by study phase/cohort.
        "phase": state.get("phase"),
        "group": state.get("group"),
        # Migration 021: where in the course this happened. Read from the same section context
        # the prompt is grounded in, so the decision and the content it was about stay joined.
        **content_coords(state.get("content_context")),
        "payload": {
            "action_type": strategy["action_type"],
            "urgency": strategy["urgency"],
            "affect_state": affect_state,
            "detection_mode": state.get("detection_mode"),
            "fallback": strategy["fallback"],
            "fallback_reason": strategy.get("fallback_reason"),
            # WHY the strategist chose this action.
            #
            # Already parsed and capped at 300 chars just above, then discarded -- so the research
            # record held what the agent decided but never its stated reason, which is the half a
            # reviewer actually needs to judge whether the decision was sound. On the fallback path
            # this is the deterministic rule's description rather than model output; `fallback`
            # distinguishes the two, so a reader is never misled about where the reason came from.
            "reason": strategy.get("reason") or None,
            # What the Pedagogical agent delegated to its Video sub-agent, when it chose a video.
            "video_brief": strategy.get("video_brief"),
        },
    })

    return {"strategy": strategy}
