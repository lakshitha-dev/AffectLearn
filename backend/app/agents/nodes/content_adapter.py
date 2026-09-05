"""Content Adapter node (Story 5.2 — real logic; was a stub in Story 4.4).

Agent 4 of the loop, and the SECOND node to call the fine-tuned LLM. On the Phase B /
adaptive branch it executes the strategist's decision (`AgentState.strategy.action_type`,
Story 5.1) by turning it into the actual learner-facing artifact and writing it to
`AgentState.adaptation_content` = `{text, variant, metadata}` for Story 5.3's `deliver`
node to push over the WebSocket.

Two execution paths plus a no-op (epics 942-952; the partition lives in `fallbacks.py`):

* GENERATIVE actions (`show_hint`, `show_alternative`, `show_breakdown`,
  `show_encouragement`, `suggest_break`, `simplify`) -> call vLLM via the SHARED
  `app.agents.llm.get_chat_client()` (Story 5.1; do NOT introduce a second client) to
  produce warm, conversational, never-clinical text shaped by the action.
* SELECTIVE actions (`skip_ahead`, `increase_difficulty`) -> do NOT call the LLM; emit a
  *selection descriptor* (`metadata.select`) pointing at an existing content variant. The
  real variant catalog is a forward concern (Open Question #3), so we hand 5.3/5.6 a
  ready pointer rather than inventing prose.
* `no_action` (or a missing/unusable strategy) -> write NO `adaptation_content`
  (return `{}`); the cycle ends with no intervention.

Resilience (NFR22; architecture line 632): like the strategist, the generative path
CATCHES its own vLLM failures — timeout, error, or empty/whitespace output — and falls
back to the deterministic `fallbacks.rule_based_content`, tagging `metadata.fallback=True`
with a `metadata.fallback_reason` (`timeout` | `vllm_error` | `parse_error`). The node
NEVER raises, so a Phase B cycle always yields usable content (or a clean `{}`).
`asyncio.wait_for(..., settings.VLLM_TIMEOUT_SECONDS)` is the SOLE timeout enforcer (the
shared client carries no internal timeout — see `llm.py`), so a slow vLLM is classified
`timeout`, never mislabeled `vllm_error`.

Every produced adaptation (LLM or fallback, generative or selective) emits an
`adaptation_triggered` research event via `research_logger.emit` (non-blocking,
sequence-numbered, never raises). `no_action` emits nothing.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents import fallbacks
from app.agents.llm import get_chat_client
from app.agents.state import AgentState
from app.core.config import settings
from app.services.research_logger import content_coords
from app.services.research_logger import emit as emit_research_event

logger = structlog.get_logger(__name__)

#: Longest adaptation text written to the research record, in characters.
#:
#: Sized well above what VLLM_MAX_TOKENS can produce, so a hit signals a generator fault rather
#: than a normal long hint. The record is append-only research data, not a cache, so it stores the
#: learner-visible string verbatim rather than a hash -- a hash cannot answer "was this hint any
#: good", which is the question the text exists to support.
_TEXT_RECORD_CAP = 4000

_SYSTEM_PROMPT = (
    "You are the Content Adapter for an adaptive e-learning platform. You write short, "
    "warm, conversational messages directly to a learner who is studying. Always use the "
    "second person ('you'), sound human and encouraging, and NEVER sound clinical or "
    "robotic. Never mention the system, the detection mechanism, or words like "
    "'difficulty reduced' or 'intervention'. Reply with ONLY the message text the learner "
    "should see — no labels, no preamble, no quotation marks.\n"
    "The section may pose questions to the learner, in prose or as an exercise. NEVER answer "
    "them. Help the learner reason toward the answer themselves — a hint that states the "
    "answer removes the thinking the question was set to provoke.\n"
    "Write PLAIN TEXT ONLY. No markdown: no **bold**, no headings, no bullet characters. The UI "
    "renders your reply verbatim, so markdown syntax reaches the learner as literal asterisks.\n"
    "Be BRIEF. This appears in a small popup over the lesson, not on a page of its own — keep it "
    "under 80 words (a step-by-step breakdown: at most 4 short steps). A long message overflows "
    "the card and buries the point."
)

# Per-action instruction appended to the user prompt to enforce the AC content shape
# (epics 943-947). Tone guidance lives in the system prompt above.
_ACTION_INSTRUCTION: dict[str, str] = {
    "show_hint": (
        "Give a brief hint: 1-2 sentences offering a simplified explanation or an analogy "
        "that nudges the learner toward the idea without giving the full answer."
    ),
    "show_alternative": (
        "Explain the current concept again from a different angle — a full alternative "
        "explanation that may click better than the original framing."
    ),
    "show_breakdown": (
        "Break the concept down into a clear, numbered step-by-step walkthrough so the "
        "learner can follow it one piece at a time."
    ),
    "show_encouragement": (
        "Offer one warm, brief line of encouragement to keep the learner motivated."
    ),
    "suggest_break": (
        "Gently suggest the learner take a short break to rest and recharge. Keep it "
        "caring and brief."
    ),
    "simplify": (
        "Re-explain the current concept more gently, at a lower cognitive load — simpler "
        "words and smaller steps, with a brief encouraging tone."
    ),
}


def _build_human_prompt(action_type: str, profile: dict, content_context: dict) -> str:
    """Compact, token-efficient context block + the per-action instruction.

    Includes the section's actual text (`content_context["body"]`, built by
    `services.content_context_service`) when available. Without it the model only ever saw a
    topic label — and until 2026-08-29 not even that, because no call site populated
    `content_context` at all, so every prompt read `content_topic: unknown`. A hint that cannot
    name what the learner is reading is indistinguishable from the rule-based fallback.

    The body is already truncated to a character budget upstream; it is NOT re-truncated here so
    there is a single place that decides how much context a prompt carries.
    """
    topic = content_context.get("topic", "unknown")
    difficulty = content_context.get("difficulty", "unknown")
    lesson = content_context.get("lesson")
    body = (content_context.get("body") or "").strip()
    instruction = _ACTION_INSTRUCTION.get(action_type, "Help the learner with this topic.")

    lines = [f"content_topic: {topic}"]
    if lesson and lesson != "unknown":
        lines.append(f"lesson: {lesson}")
    lines.append(f"content_difficulty: {difficulty}")
    lines.append(f"learner_skill_level: {profile.get('skill_level', 'unknown')}")
    if body:
        # Fenced so the model treats it as material to reason about, not as instructions to it.
        lines.append(f"\nThe learner is currently reading this section:\n---\n{body}\n---")
    lines.append(f"\nTask: {instruction}")
    if body:
        lines.append(
            "Ground your message in the section above — refer to its actual concepts and "
            "terms rather than giving generic study advice."
        )
    return "\n".join(lines)


_MD_INLINE = re.compile(r"(\*\*|__|`)")
_MD_LEADING = re.compile(r"^\s{0,3}(#{1,6}\s+|[-*+]\s+)", re.MULTILINE)


def _strip_markdown(text: str) -> str:
    """Remove markdown syntax the UI would show verbatim. Pure; never raises.

    `AdaptiveHintCallout` renders the reply as plain text, so `**bold**` and backticked code reach
    the learner as literal asterisks and backticks. Observed in production: a delivered breakdown
    read "**Class and Main Method**: The program starts with a class named `Report`".

    The system prompt already forbids markdown, and that IS enough for `show_hint`. It is NOT
    enough for `show_breakdown`, where a numbered list with bold labels is the model's natural
    format and it reverts to it regardless of instruction. An instruction can be ignored; this
    cannot — so both layers exist, the same belt-and-braces approach used for the answer leak.

    Numbering (`1.`, `2.`) is deliberately PRESERVED: the callout parses it into an ordered list.
    """
    text = _MD_INLINE.sub("", text)
    text = _MD_LEADING.sub("", text)
    return text.strip()


def _content_text(content: Any) -> str:
    """Normalise a chat message's content to a string (str or list-of-blocks).

    Mirrors `pedagogical._content_text` — kept local so the two nodes stay independent.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # content blocks (newer langchain)
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(content or "")


async def _generate(
    action_type: str, profile: dict, content_context: dict
) -> dict[str, Any]:
    """Produce generative `adaptation_content` for one action. Never raises.

    Tries vLLM under `asyncio.wait_for`; on timeout / error / empty-or-unusable output
    it falls back to `fallbacks.rule_based_content`, tagging `fallback`/`fallback_reason`.
    """
    context = {
        "topic": content_context.get("topic"),
        "difficulty": content_context.get("difficulty"),
        "skill_level": profile.get("skill_level"),
    }

    def _fallback(reason: str) -> dict[str, Any]:
        content = fallbacks.rule_based_content(action_type, context)
        content["metadata"] = {
            **content["metadata"],
            "generated": False,
            "fallback": True,
            "fallback_reason": reason,
        }
        return content

    try:
        client = get_chat_client()
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=_build_human_prompt(action_type, profile, content_context)),
        ]
        resp = await asyncio.wait_for(
            client.ainvoke(messages), timeout=settings.VLLM_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        logger.warning("content_adapter_vllm_timeout", action_type=action_type)
        return _fallback("timeout")
    except Exception as exc:  # noqa: BLE001 — degrade on any vLLM/client error (NFR22)
        logger.warning("content_adapter_vllm_error", action_type=action_type, error=str(exc))
        return _fallback("vllm_error")

    text = _strip_markdown(_content_text(getattr(resp, "content", resp)))
    if not text:
        logger.warning("content_adapter_parse_error", action_type=action_type)
        return _fallback("parse_error")

    return {
        "text": text,
        "variant": action_type,
        "metadata": {"action_type": action_type, "generated": True, "fallback": False},
    }


async def content_adapter_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: turn the strategist's decision into `adaptation_content`.

    Returns a partial state update `{"adaptation_content": {...}}` for generative and
    selective actions, or `{}` for `no_action` / a missing strategy. Never raises (NFR22).
    """
    strategy = state.get("strategy") or {}
    action_type = strategy.get("action_type")
    affect_state = state.get("affect_state")
    profile = state.get("learner_profile") or {}
    content_context = state.get("content_context") or {}

    # no_action (or no/empty strategy) -> no intervention this cycle, no event.
    if action_type is None or action_type == "no_action":
        return {}

    if action_type in fallbacks.SELECTIVE_ACTIONS:
        content = fallbacks.rule_based_content(action_type, content_context)
        content["metadata"] = {
            **content["metadata"],
            "generated": False,
            "fallback": False,
        }
    elif action_type in fallbacks.GENERATIVE_ACTIONS:
        content = await _generate(action_type, profile, content_context)
    else:
        # Out-of-partition action_type (should not happen — vocabulary is locked).
        logger.warning("content_adapter_unknown_action", action_type=action_type)
        return {}

    # Stamp shared affect provenance into metadata (consumed by 5.3 / UI).
    content["metadata"]["affect_state"] = affect_state

    md = content["metadata"]
    logger.info(
        "adaptation_triggered",
        learner_id=state.get("learner_id"),
        cycle=state.get("cycle_number"),
        action_type=action_type,
        variant=content["variant"],
        generated=md.get("generated"),
        fallback=md.get("fallback"),
    )
    await emit_research_event({
        "event_type": "adaptation_triggered",
        "learner_id": state.get("learner_id"),
        "session_id": state.get("session_id"),
        "cycle_number": state.get("cycle_number") or 0,
        "timestamp": int(time.time() * 1000),
        # Story 6.5: top-level phase/group so the event is filterable by study phase/cohort.
        "phase": state.get("phase"),
        "group": state.get("group"),
        # Migration 021: where in the course this happened. Read from the same section context
        # the prompt is grounded in, so the decision and the content it was about stay joined.
        **content_coords(state.get("content_context")),
        "payload": {
            "action_type": action_type,
            "variant": content["variant"],
            "affect_state": affect_state,
            "detection_mode": state.get("detection_mode"),
            "generated": bool(md.get("generated")),
            "fallback": bool(md.get("fallback")),
            "fallback_reason": md.get("fallback_reason"),
            # WHAT THE LEARNER WAS SHOWN.
            #
            # This existed only in AgentState for the duration of one ainvoke and was then
            # garbage-collected, so the research record could say an adaptation was delivered but
            # never what it said. For pre-written content that was recoverable from the fallback
            # copy; for LLM-generated content it was gone permanently, which makes "did this hint
            # help" unanswerable for exactly the content the study is about.
            #
            # Capped rather than truncated silently: the cap is generous against the model's own
            # max_tokens, so hitting it means the generator misbehaved, and `text_truncated` says
            # so instead of leaving a reader to wonder whether the learner saw a clipped hint.
            "text": (content.get("text") or "")[:_TEXT_RECORD_CAP] or None,
            "text_truncated": len(content.get("text") or "") > _TEXT_RECORD_CAP,
        },
    })

    return {"adaptation_content": content}
