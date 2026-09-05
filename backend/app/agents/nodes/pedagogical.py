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
from app.agents.state import AFFECT_STATES, AgentState
from app.core.config import settings
from app.services.research_logger import content_coords
from app.services.research_logger import emit as emit_research_event

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are the Pedagogical Strategist for an adaptive e-learning platform. Given a "
    "learner's current affective state, their profile, and the content they are studying, "
    "decide the single best teaching intervention.\n\n"
    "Reply with ONLY a JSON object: "
    '{"action_type": <action>, "reason": <short string>, "urgency": "low"|"medium"|"high"}.\n'
    f"action_type MUST be one of: {', '.join(fallbacks.ACTION_TYPES)}.\n\n"
    "Guidance:\n"
    "- confused: show_hint (first/mild), show_alternative (sustained), or show_breakdown "
    "(deep confusion on conceptual content).\n"
    "- frustrated: show_encouragement or simplify (moderate); suggest_break "
    "(high/extended, especially late sessions).\n"
    "- bored: skip_ahead or increase_difficulty to re-engage.\n"
    "- engaged: no_action, or increase_difficulty only if engagement is sustained.\n"
    "Use the learner profile (skill level, mastery, recent affect history) and content "
    "difficulty to choose. Prefer no_action over an unhelpful interruption."
)


def _build_human_prompt(
    affect_state: str,
    affect_confidence: Any,
    profile: dict,
    content_context: dict,
) -> str:
    """Compact, token-efficient context block for the LLM.

    Deliberately carries the section/lesson TITLES but not the section body, unlike
    `content_adapter._build_human_prompt`. The strategist only picks an `action_type` from a
    locked vocabulary — a classification. Feeding it the full ~2000-char body would roughly
    double the prompt for every cycle without changing which of nine actions it chooses. The
    adapter is the node that writes learner-facing prose, so that is where the body belongs.
    """
    topic = content_context.get("topic", "unknown")
    difficulty = content_context.get("difficulty", "unknown")
    lesson = content_context.get("lesson")
    recent = (profile.get("affect_history") or [])[-5:]
    lesson_line = f"content_lesson: {lesson}\n" if lesson and lesson != "unknown" else ""
    return (
        f"affect_state: {affect_state}\n"
        f"affect_confidence: {affect_confidence}\n"
        f"skill_level: {profile.get('skill_level', 'unknown')}\n"
        f"topic_mastery: {profile.get('topic_mastery', {}).get(topic, 'unknown')}\n"
        f"format_preferences: {profile.get('format_preferences', {})}\n"
        f"recent_affect_history: {recent}\n"
        f"{lesson_line}"
        f"content_topic: {topic}\n"
        f"content_difficulty: {difficulty}"
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
    return {
        "action_type": action_type,
        "reason": str(obj.get("reason", ""))[:300],
        "urgency": urgency,
    }


async def _decide(
    affect_state: str | None,
    affect_confidence: Any,
    profile: dict,
    content_context: dict,
) -> dict[str, Any]:
    """Produce a strategy dict (with `fallback`/`fallback_reason` provenance). Never raises."""
    # No usable affect this cycle (e.g. empty/face-less cycle that still routed here):
    # skip the LLM and take the safe no_action rule.
    if affect_state not in AFFECT_STATES:
        strat = fallbacks.rule_based_strategy(affect_state, profile)
        return {**strat, "fallback": True, "fallback_reason": "no_affect"}

    try:
        client = get_chat_client()
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=_build_human_prompt(affect_state, affect_confidence, profile, content_context)
            ),
        ]
        resp = await asyncio.wait_for(
            client.ainvoke(messages), timeout=settings.VLLM_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        logger.warning("pedagogical_vllm_timeout", affect_state=affect_state)
        strat = fallbacks.rule_based_strategy(affect_state, profile)
        return {**strat, "fallback": True, "fallback_reason": "timeout"}
    except Exception as exc:  # noqa: BLE001 — degrade on any vLLM/client error (NFR22)
        logger.warning("pedagogical_vllm_error", affect_state=affect_state, error=str(exc))
        strat = fallbacks.rule_based_strategy(affect_state, profile)
        return {**strat, "fallback": True, "fallback_reason": "vllm_error"}

    parsed = _parse_strategy(_content_text(getattr(resp, "content", resp)))
    if parsed is None:
        logger.warning("pedagogical_parse_error", affect_state=affect_state)
        strat = fallbacks.rule_based_strategy(affect_state, profile)
        return {**strat, "fallback": True, "fallback_reason": "parse_error"}

    return {**parsed, "fallback": False}


async def pedagogical_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: decide and write the intervention `strategy`. Never raises (NFR22)."""
    affect_state = state.get("affect_state")
    cycle = state.get("cycle_number")
    profile = state.get("learner_profile") or {}
    content_context = state.get("content_context") or {}

    strategy = await _decide(affect_state, state.get("affect_confidence"), profile, content_context)

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
        },
    })

    return {"strategy": strategy}
