"""Video Resource Agent: find one short YouTube explanation for what the learner is stuck on.

WHY THIS EXISTS

The confusion ladder ends at "a different explanation", and every rung is text. A learner who is
still stuck after three pieces of text often needs a different MEDIUM rather than a fourth
paragraph: someone working the idea through on screen. This agent supplies that on request.

HOW IT DECIDES (three steps, each with a deterministic fallback)

1. QUERY  -- the language model reads the section (topic, lesson, excerpt), what the learner did
             there (wrong answers, re-reading) and the hint they have already seen, and writes a
             YouTube search query plus the concept it targets. Fallback: "<topic> <lesson>
             explained".
2. SEARCH -- YouTube Data API v3: `search.list` for embeddable, safe-search-strict videos, then
             `videos.list` for their durations, keeping 2 to 15 minutes. A lesson-sized
             explanation, not a two-hour course and not a thirty-second short.
3. CHOOSE -- the model ranks the candidates' titles and descriptions against the concept and names
             one, with a one-line reason the learner sees. Fallback: the top search result.

WHERE IT RUNS

As the Pedagogical agent's SUB-AGENT: when the strategist chooses `show_video` it writes a brief
(`{concept, query}`) and delegates, and `nodes/video_resource.py` runs this in parallel with the
Content Adapter, so the strategist never waits on YouTube. With a brief, step 1 is skipped.

And on demand, when the learner clicks "Watch a video explanation" on any confusion card -- a REST
call with no brief, so the sub-agent writes its own query. Neither path runs in the detection
path, so nothing here can move a gate or trial statistic.

COST AND FAILURE

A search costs 100 quota units of a free 10,000/day, so results are cached per section and concept
for a week and shared by every learner. With no key, an exhausted quota, a timeout or an empty
result, the learner gets a YouTube search link built from the agent's query instead of an embed.
`find_video` never raises: a broken video lookup must cost the video, never the lesson (NFR22).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any
from urllib.parse import quote_plus

import httpx
import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import get_chat_client
from app.core.config import settings
from app.services import learner_activity, redis_service

logger = structlog.get_logger(__name__)

_API = "https://www.googleapis.com/youtube/v3"
_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
_MIN_DURATION_S = 120
_MAX_DURATION_S = 15 * 60
_MAX_CANDIDATES = 8
#: Per-step budgets. Two model calls and two HTTP calls must fit VIDEO_HELP_TIMEOUT_SECONDS.
_LLM_STEP_TIMEOUT_S = 3.0
#: Ranking eight titles is a small job, and the top search result is already a good answer, so the
#: choose step gives up sooner. Measured locally with no model: 1s search + a 3s choose wait
#: overran the sub-agent's in-cycle budget and turned an available video into a pending one.
_CHOOSE_TIMEOUT_S = 2.0
_HTTP_TIMEOUT_S = 4.0

_QUERY_PROMPT = (
    "You help a learner who is stuck find ONE short YouTube explanation video.\n"
    "Given the section they are studying, what they did, and the hint they already saw, write the "
    "YouTube search query most likely to find a clear beginner-friendly explanation of the exact "
    "idea they are stuck on. Reply with ONLY JSON: "
    '{"query": <4-10 word search query>, "concept": <the idea in 3-6 words>}. '
    "No channel names, no quotes inside the query."
)

_CHOOSE_PROMPT = (
    "You pick the ONE video that best explains a concept to a stuck learner. Prefer a focused "
    "explanation of exactly that concept from an educational channel over a general course, a "
    "reaction video or clickbait. Reply with ONLY JSON: "
    '{"video_id": <one id from the list>, "reason": <one short sentence, addressed to the '
    'learner, saying why this video will help>}.'
)


# ── pure helpers ─────────────────────────────────────────────────────────────────────


def _flat(text: Any, limit: int) -> str:
    """Collapse whitespace and cut at a word boundary. Pure."""
    s = " ".join(str(text or "").split())
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(" ", 1)[0]


def fallback_query(content_context: dict[str, Any]) -> tuple[str, str]:
    """A deterministic (query, concept) from the section's own labels. Pure."""
    topic = str(content_context.get("topic") or "").strip()
    lesson = str(content_context.get("lesson") or "").strip()
    parts = [p for p in (topic, lesson) if p and p.lower() != "unknown"]
    concept = " ".join(dict.fromkeys(parts)) or "this concept"
    return f"{concept} explained", concept


_DURATION = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def parse_duration(iso: Any) -> int | None:
    """ISO-8601 video duration ("PT4M13S") to seconds, or None. Pure."""
    m = _DURATION.match(str(iso or ""))
    if not m or not any(m.groups()):
        return None
    h, mi, s = (int(g) if g else 0 for g in m.groups())
    return h * 3600 + mi * 60 + s


def search_link(query: str) -> str:
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


def _json_object(text: str) -> dict[str, Any] | None:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def _content_text(resp: Any) -> str:
    content = getattr(resp, "content", resp)
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content or "")


def _cache_key(section_id: Any, concept: str) -> str:
    digest = hashlib.sha1(concept.lower().encode("utf-8")).hexdigest()[:16]
    return f"video_help:{section_id}:{digest}"


# ── steps ────────────────────────────────────────────────────────────────────────────


async def _ask(
    system: str, human: str, timeout_s: float = _LLM_STEP_TIMEOUT_S
) -> dict[str, Any] | None:
    """One model call returning a JSON object, or None on any failure. Never raises."""
    try:
        resp = await asyncio.wait_for(
            get_chat_client().ainvoke([SystemMessage(content=system), HumanMessage(content=human)]),
            timeout=timeout_s,
        )
    except Exception as exc:  # noqa: BLE001 -- timeout, network, auth: all mean "fall back"
        logger.info("video_agent_llm_unavailable", error=type(exc).__name__)
        return None
    return _json_object(_content_text(resp))


async def build_query(
    content_context: dict[str, Any], last_hint_text: str | None
) -> tuple[str, str, bool]:
    """(query, concept, from_model). Falls back to the section labels. Never raises."""
    activity = learner_activity.describe(content_context.get("learner_activity"))
    human = "\n".join(filter(None, [
        f"topic: {content_context.get('topic', 'unknown')}",
        f"lesson: {content_context.get('lesson', 'unknown')}",
        f"section_excerpt: {_flat(content_context.get('body'), 600)}",
        f"learner_activity: {activity}" if activity else "",
        f"hint_already_shown: {_flat(last_hint_text, 400)}" if last_hint_text else "",
    ]))
    obj = await _ask(_QUERY_PROMPT, human)
    query = _flat((obj or {}).get("query"), 120)
    concept = _flat((obj or {}).get("concept"), 80)
    if query and concept:
        return query, concept, True
    fq, fc = fallback_query(content_context)
    return fq, fc, False


async def search(query: str, api_key: str) -> list[dict[str, Any]]:
    """Embeddable, safe, 2-15 minute candidates for `query`. Raises on HTTP failure."""
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
        r = await client.get(f"{_API}/search", params={
            "part": "snippet", "q": query, "type": "video", "videoEmbeddable": "true",
            "safeSearch": "strict", "relevanceLanguage": "en",
            "maxResults": _MAX_CANDIDATES, "key": api_key,
        })
        r.raise_for_status()
        items = r.json().get("items") or []
        ids = [i.get("id", {}).get("videoId") for i in items if i.get("id", {}).get("videoId")]
        if not ids:
            return []
        d = await client.get(f"{_API}/videos", params={
            "part": "contentDetails,snippet,status", "id": ",".join(ids), "key": api_key,
        })
        d.raise_for_status()

    out: list[dict[str, Any]] = []
    for v in d.json().get("items") or []:
        seconds = parse_duration((v.get("contentDetails") or {}).get("duration"))
        if seconds is None or not (_MIN_DURATION_S <= seconds <= _MAX_DURATION_S):
            continue
        if (v.get("status") or {}).get("embeddable") is False:
            continue
        sn = v.get("snippet") or {}
        out.append({
            "video_id": v.get("id"),
            "title": sn.get("title") or "",
            "channel": sn.get("channelTitle") or "",
            "description": _flat(sn.get("description"), 200),
            "duration_s": seconds,
        })
    # Keep search relevance order, which videos.list does not preserve.
    order = {vid: i for i, vid in enumerate(ids)}
    out.sort(key=lambda c: order.get(c["video_id"], len(order)))
    return out


async def choose(concept: str, candidates: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    """(chosen candidate, reason). Falls back to the top result. Never raises."""
    listing = "\n".join(
        f"- id={c['video_id']} | {c['title']} | {c['channel']} | {c['duration_s'] // 60} min | "
        f"{c['description']}"
        for c in candidates
    )
    obj = await _ask(
        _CHOOSE_PROMPT, f"concept: {concept}\ncandidates:\n{listing}", _CHOOSE_TIMEOUT_S
    )
    by_id = {c["video_id"]: c for c in candidates}
    picked = by_id.get((obj or {}).get("video_id"))
    if picked is not None:
        reason = _flat(obj.get("reason"), 200) or f"A short walkthrough of {concept}."
        return picked, reason
    return candidates[0], f"A short walkthrough of {concept}."


# ── the agent ────────────────────────────────────────────────────────────────────────


def clean_brief(brief: Any) -> dict[str, str] | None:
    """A usable `{concept, query}` delegation brief, or None. Pure."""
    if not isinstance(brief, dict):
        return None
    concept = _flat(brief.get("concept"), 80)
    query = _flat(brief.get("query"), 120)
    return {"concept": concept, "query": query} if concept and query else None


async def find_video(
    content_context: dict[str, Any] | None,
    last_hint_text: str | None = None,
    brief: dict[str, Any] | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """One video (embed) or a search link for what the learner is stuck on. Never raises.

    `brief` is the delegation from the Pedagogical agent (`{concept, query}`). When present the
    sub-agent skips its own query step: the strategist has already read the learner's evidence and
    written the search, so a second model call would only cost time and could only drift from it.
    """
    context = content_context or {}
    try:
        return await asyncio.wait_for(
            _find(context, last_hint_text, clean_brief(brief)),
            timeout=timeout_s or settings.VIDEO_HELP_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 -- including the overall timeout
        logger.warning("video_agent_failed", error=type(exc).__name__)
        query, concept = fallback_query(context)
        return _link(query, concept, "fallback")


def _link(query: str, concept: str, source: str) -> dict[str, Any]:
    return {
        "kind": "link", "url": search_link(query), "query": query, "concept": concept,
        "reason": f"Browse short videos explaining {concept}.", "source": source,
    }


async def _find(
    context: dict[str, Any], last_hint_text: str | None, brief: dict[str, str] | None = None
) -> dict[str, Any]:
    if brief:
        query, concept, from_model = brief["query"], brief["concept"], True
    else:
        query, concept, from_model = await build_query(context, last_hint_text)
    section_id = context.get("section_id")

    key = _cache_key(section_id, concept) if section_id else None
    if key:
        cached = await redis_service.get_json(key)
        if isinstance(cached, dict) and cached.get("video_id"):
            return {**cached, "source": "cache"}

    api_key = (settings.YOUTUBE_API_KEY or "").strip()
    if not api_key:
        return _link(query, concept, "search_link")

    try:
        candidates = await search(query, api_key)
    except Exception as exc:  # noqa: BLE001 -- quota, key, network
        logger.warning("video_agent_search_failed", error=type(exc).__name__)
        return _link(query, concept, "search_link")
    if not candidates:
        return _link(query, concept, "search_link")

    if from_model:
        picked, reason = await choose(concept, candidates)
    else:
        # The model already failed once on this request. Asking it again would spend a second
        # full step timeout and, with the search in between, overrun VIDEO_HELP_TIMEOUT_SECONDS --
        # turning "no model" into "no video" when the top search result was right there.
        picked, reason = candidates[0], f"A short walkthrough of {concept}."
    result = {
        "kind": "embed",
        "video_id": picked["video_id"],
        "title": picked["title"],
        "channel": picked["channel"],
        "duration_s": picked["duration_s"],
        "url": f"https://www.youtube.com/watch?v={picked['video_id']}",
        "query": query,
        "concept": concept,
        "reason": reason,
        "query_from_model": from_model,
        "source": "api",
    }
    if key:
        await redis_service.set_json(key, result, ttl_seconds=_CACHE_TTL_SECONDS)
    return result
