"""Build the `AgentState.content_context` the pedagogical agents need to write grounded hints.

Nothing populated this before. `make_initial_state` accepts a `content_context` argument
(`state.py:94`) but BOTH call sites in `ws.py` (lines 191 and 302) omit it, so it defaulted to
`{}` on every cycle. The downstream effect is visible in the prompt built by
`content_adapter._build_human_prompt` (line 91):

    content_topic: unknown
    content_difficulty: unknown
    learner_skill_level: unknown

An LLM given that cannot say anything specific about the lesson, so even a perfectly healthy
vLLM would return generic filler. That is why the delivered hint read "try connecting it to
something you already know well" — indistinguishable from the rule-based fallback it sits next to.

This module turns a `section_id` into real grounding: the section title, its parent lesson title,
and a truncated plain-text rendering of the section's content blocks.

Caching: course content is static for the life of a process (authored by designers, not learners),
and the alternative is two joins on every 30s affect cycle for every concurrent learner. The cache
is keyed by section id and never invalidated in-process — a designer editing a section will not see
it reflected until restart, which is an acceptable trade for a research pilot and is called out here
so it is not mistaken for a bug.

Never raises: a grounding lookup must not be able to break an affect cycle (NFR22). Every failure
path returns a usable dict, degrading to `{}` rather than propagating.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.course import ContentBlock, Lesson, Section

logger = structlog.get_logger(__name__)

# Character budget for the rendered section body. The reply is capped at
# `VLLM_MAX_TOKENS=256`, and the strategist/adapter prompts are otherwise tiny, so this leaves
# ample room inside a 4096-token context while still carrying the substance of a section.
# Characters (not tokens) because it is a cheap, dependency-free bound; ~4 chars/token puts this
# near 500 tokens worst case.
_BODY_CHAR_BUDGET = 2000

# section_id -> built context. See "Caching" in the module docstring.
_cache: dict[str, dict[str, Any]] = {}


def _reset_cache() -> None:
    """Test helper — drop the memoised contexts."""
    _cache.clear()


def _block_text(block: ContentBlock) -> str:
    """Render one content block as plain text for the prompt. Never raises.

    Mirrors the authoring helpers in `db/course_content_helpers.py`, which is the single source
    of truth for these shapes:
        text     -> {"text": ...}
        code     -> {"language": ..., "code": ...}
        callout  -> {"variant": ..., "text": ...}
        quiz     -> {"question": ..., "options": [...]}
        exercise -> {"prompt": ..., "answer": ..., "explanation": ...}

    Answers are deliberately EXCLUDED: the adapter's job is to hint, and `_ACTION_INSTRUCTION`
    for `show_hint` says "without giving the full answer". Feeding it the answer key invites
    exactly the leak the instruction forbids.
    """
    content = block.content if isinstance(block.content, dict) else {}
    kind = getattr(block.block_type, "value", block.block_type)

    if kind == "text":
        return str(content.get("text") or "")
    if kind == "callout":
        return str(content.get("text") or "")
    if kind == "code":
        lang = str(content.get("language") or "")
        code = str(content.get("code") or "")
        return f"[{lang} code]\n{code}" if code else ""
    if kind == "quiz":
        return f"[quiz] {content.get('question') or ''}"
    if kind == "exercise":
        # prompt only — never `answer`.
        return f"[exercise] {content.get('prompt') or ''}"
    return ""


def _render_body(blocks: list[ContentBlock]) -> str:
    """Join blocks in author order, bounded by `_BODY_CHAR_BUDGET`.

    Truncation is marked so the model can tell the section continues rather than treating a
    mid-sentence cut as the end of the material.
    """
    parts: list[str] = []
    used = 0
    for block in sorted(blocks, key=lambda b: b.sort_order or 0):
        text = _block_text(block).strip()
        if not text:
            continue
        if used + len(text) > _BODY_CHAR_BUDGET:
            remaining = _BODY_CHAR_BUDGET - used
            if remaining > 80:  # only worth including a fragment if it carries meaning
                parts.append(text[:remaining].rstrip() + " …[section continues]")
            else:
                parts.append("…[section continues]")
            break
        parts.append(text)
        used += len(text)
    return "\n\n".join(parts)


async def build(section_id: Any, db: AsyncSession) -> dict[str, Any]:
    """Return `{topic, lesson, body, difficulty}` for a section id. Never raises.

    Returns `{}` when `section_id` is missing or unknown, which keeps the existing
    "unknown topic" behaviour rather than inventing content.

    `difficulty` is always `"unknown"`: no difficulty field exists on Course, Lesson or Section
    (checked 2026-08-29). It is still emitted so the prompt shape stays stable if one is added.
    """
    if not section_id:
        return {}

    key = str(section_id)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    try:
        result = await db.execute(
            select(Section)
            .options(selectinload(Section.content_blocks), selectinload(Section.lesson))
            .where(Section.id == section_id)
        )
        section = result.scalar_one_or_none()
    except Exception:  # noqa: BLE001 — grounding must never break a cycle (NFR22)
        logger.warning("content_context_lookup_failed", section_id=key, exc_info=True)
        return {}

    if section is None:
        logger.warning("content_context_section_not_found", section_id=key)
        return {}

    lesson: Lesson | None = getattr(section, "lesson", None)
    context = {
        "topic": section.title or "unknown",
        "lesson": (lesson.title if lesson is not None else None) or "unknown",
        "body": _render_body(list(section.content_blocks or [])),
        "difficulty": "unknown",
    }
    _cache[key] = context
    return context
