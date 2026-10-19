"""Content Adapter node (Story 5.2 — real logic; was a stub in Story 4.4).

Agent 4 of the loop, and the SECOND node to call the fine-tuned LLM. On the Phase B /
adaptive branch it executes the strategist's decision (`AgentState.strategy.action_type`,
Story 5.1) by turning it into the actual learner-facing artifact and writing it to
`AgentState.adaptation_content` = `{text, variant, metadata}` for Story 5.3's `deliver`
node to push over the WebSocket.

Two execution paths plus a no-op (epics 942-952; the partition lives in `fallbacks.py`):

* GENERATIVE actions (`show_hint`, `show_alternative`, `show_breakdown`, `increase_difficulty`,
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
from app.services import learner_activity
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
    # The last confusion rung. The video itself is found by the Video sub-agent in parallel; this
    # is only the line that introduces it, so it must not try to explain the idea again in text.
    "show_video": (
        "The learner has already had text explanations of this and is still stuck, so a short "
        "video is being shown. Write ONE or TWO short sentences introducing it: name the exact "
        "idea from the section that the video will walk through, and say that watching it worked "
        "through can help. Do not explain the idea yourself and do not give any answer."
    ),
    # The boredom response. Flow theory places boredom at challenge BELOW skill, so this must
    # actually RAISE difficulty rather than re-present the same material more loudly. Asking a
    # question also makes the intervention measurable: a question can be answered or ignored,
    # where a statement can only be dismissed.
    "increase_difficulty": (
        "The learner already understands this and is disengaging from being under-challenged. "
        "Pose ONE short, genuinely harder question about the section above — an edge case, a "
        "'why does this work', or a case where the idea breaks down. Do NOT give the answer, "
        "do not restate the section, and keep it to a single question the learner can attempt "
        "right now without leaving the page."
    ),
}


def _build_human_prompt(
    action_type: str,
    profile: dict,
    content_context: dict,
    already_shown: list[str] | None = None,
) -> str:
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
    # WHAT THE LEARNER HAS ALREADY BEEN TOLD.
    #
    # The escalation ladder stops the system repeating an ACTION; nothing stopped it
    # repeating a FRAMING. With the ladder enforced, `show_alternative` was observed
    # returning the same "think of it like a friendly greeting" analogy the `show_hint` two
    # rungs earlier had already used -- the action escalated and the learner got the same
    # explanation reworded, which is exactly what the ladder exists to prevent.
    if already_shown:
        prior = "\n".join(f"- {t}" for t in already_shown)
        lines.append(
            "\nYou have ALREADY shown this learner the following in this section:\n"
            f"{prior}"
        )

    # WHAT THE LEARNER HAS DONE HERE, observed rather than inferred: wrong answers, a revealed
    # answer, re-reading, time spent. Without it a hint for someone who has just failed the
    # section's question three times read the same as one for someone who had not tried it.
    activity = learner_activity.describe(content_context.get("learner_activity"))
    if activity:
        lines.append(f"\nWhat the learner has done in this section so far: {activity}.")

    lines.append(f"\nTask: {instruction}")

    if activity and "incorrectly" in activity:
        lines.append(
            "They have already tried and got it wrong, so aim at the likely misconception "
            "behind a wrong answer rather than restating the section. Still do not reveal the "
            "correct answer."
        )

    if already_shown:
        lines.append(
            "That did not land. Say something GENUINELY different: a different analogy, a "
            "different starting point, or a different aspect of the idea. Do not restate "
            "the messages above in other words."
        )
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


def _normalise(text: Any) -> str:
    return " ".join(str(text or "").lower().split())


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


#: Which authored variant answers which pedagogical action (FR19 / FR21).
#:
#: `content_blocks.variant_key` has existed since migration 005 and nothing ever wrote anything
#: but `"original"` into it, so every one of these actions fell through to generated prose. With
#: a catalogue behind them, a designer's own alternative wording beats an LLM paraphrase of the
#: section it is standing in for: it was written for this material, by someone who teaches it.
#:
#: `show_hint` and `show_encouragement` are deliberately absent — a hint is about the learner's
#: current difficulty, not a substitute rendering of the content, and there is nothing to select.
_ACTION_VARIANT: dict[str, str] = {
    "show_alternative": "alternative",
    "show_breakdown": "simpler",
    "simplify": "simpler",
    "increase_difficulty": "harder",
    "skip_ahead": "harder",
}


async def _authored_variant(action_type: str, state: AgentState) -> str | None:
    """The designer-authored alternative for this action, if one exists.

    Returns None — not an error — when there is no catalogue entry, no section context, or no
    database handle. Having no authored variant is the ordinary case and must degrade to the
    existing generative path rather than costing the learner an intervention.

    Never raises: this runs inside the loop, and NFR22 requires the node to always produce
    usable content.
    """
    variant_key = _ACTION_VARIANT.get(action_type)
    if variant_key is None:
        return None

    section_id = (state.get("content_context") or {}).get("section_id")
    db = state.get("db")
    if not section_id or db is None:
        return None

    try:
        from app.services import course_service

        block = await course_service.find_variant(
            db, section_id=section_id, variant_key=variant_key
        )
    except Exception:  # noqa: BLE001 — a lookup failure must not cost an intervention
        logger.warning("authored_variant_lookup_failed", exc_info=True)
        return None

    if block is None:
        return None

    text = (block.content or {}).get("text") if isinstance(block.content, dict) else None
    return text.strip() if isinstance(text, str) and text.strip() else None


async def _previously_shown(state: AgentState) -> list[str]:
    """Adaptation text this learner has already seen in this section, newest first.

    Never raises and returns an empty list on any missing piece: a prompt without this context
    still produces a usable adaptation, so a lookup failure must cost variety rather than the
    intervention itself (NFR22).

    Capped at three. The model needs enough to know what NOT to say again; the whole history
    would crowd out the section body, which is the context that makes the message specific.
    """
    section_id = (state.get("content_context") or {}).get("section_id")
    learner_id = state.get("learner_id")
    db = state.get("db")
    if not section_id or not learner_id or db is None:
        return []

    try:
        from app.services import assistance_service

        return await assistance_service.texts_shown_in_section(
            db, learner_id=learner_id, section_id=section_id, limit=3
        )
    except Exception:  # noqa: BLE001 -- variety is worth less than the intervention
        logger.warning("previously_shown_lookup_failed", exc_info=True)
        return []


async def _generate(
    action_type: str,
    profile: dict,
    content_context: dict,
    already_shown: list[str] | None = None,
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
            HumanMessage(
                content=_build_human_prompt(
                    action_type, profile, content_context, already_shown
                )
            ),
        ]
        started = time.monotonic()
        resp = await asyncio.wait_for(
            client.ainvoke(messages), timeout=settings.VLLM_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        logger.warning("content_adapter_vllm_timeout", action_type=action_type)
        return _fallback("timeout")
    except Exception as exc:  # noqa: BLE001 — degrade on any vLLM/client error (NFR22)
        logger.warning("content_adapter_vllm_error", action_type=action_type, error=str(exc))
        return _fallback("vllm_error")
    llm_ms = int((time.monotonic() - started) * 1000)

    text = _strip_markdown(_content_text(getattr(resp, "content", resp)))
    if not text:
        logger.warning("content_adapter_parse_error", action_type=action_type)
        content = _fallback("parse_error")
        content["metadata"]["llm_ms"] = llm_ms
        return content

    return {
        "text": text,
        "variant": action_type,
        "metadata": {"action_type": action_type, "generated": True, "fallback": False,
                     "llm_ms": llm_ms},
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

    # An authored variant outranks both paths: it is content a designer wrote for THIS material
    # as the alternative to show, so paraphrasing the same section with an LLM instead would be
    # choosing the weaker option. Absent one, everything below behaves exactly as before.
    authored = await _authored_variant(action_type, state)

    if action_type in fallbacks.SELECTIVE_ACTIONS:
        content = fallbacks.rule_based_content(action_type, content_context)
        content["metadata"] = {
            **content["metadata"],
            "generated": False,
            "fallback": False,
        }
        if authored is not None:
            # `skip_ahead` framing text stays; the descriptor now points at real content rather
            # than at a catalogue that did not exist.
            content["metadata"]["select"] = "authored_variant"
            content["metadata"]["authored_variant"] = True
            content["text"] = authored
    elif authored is not None:
        content = {
            "text": authored,
            "variant": action_type,
            "metadata": {
                "action_type": action_type,
                "generated": False,
                "fallback": False,
                # Distinguishes "a human wrote this" from "the rule-based copy fired", which look
                # identical on `generated=False` alone and mean very different things when reading
                # the research record.
                "authored_variant": True,
            },
        }
    elif action_type in fallbacks.GENERATIVE_ACTIONS:
        already_shown = await _previously_shown(state)
        content = await _generate(action_type, profile, content_context, already_shown)
        # The same words twice in one section is not help, it is noise. The prompt asks the model
        # not to repeat itself; the pre-written fallback copy cannot vary, so a slow model would
        # otherwise hand the learner the identical sentence again.
        if _normalise(content.get("text")) in {_normalise(t) for t in already_shown}:
            logger.info("adaptation_skipped_duplicate_text", action_type=action_type)
            return {}
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
            # Which model wrote the text and how long it took (None when no call was made).
            "llm_model": settings.VLLM_MODEL if md.get("llm_ms") is not None else None,
            "llm_ms": md.get("llm_ms"),
            # Whether the learner saw designer-authored content or machine-written prose. Without
            # this the record cannot separate the two, and "did the adaptation help" is a
            # different question for each.
            "authored_variant": bool(md.get("authored_variant")),
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
