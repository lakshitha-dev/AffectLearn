"""Offline evaluation of the deployed Pedagogical Agent and Content Adapter LLM nodes.

WHAT IT MEASURES
----------------
The two nodes that call the LLM, as deployed. The harness calls `pedagogical.pedagogical_node`
and `content_adapter.content_adapter_node` themselves, so the prompts are built by the real
`_build_human_prompt` functions, the strategy is parsed by the real `_parse_strategy`, the real
code overrides (`_enforce_escalation`, `_honour_request`) run, the adapter's markdown strip and
both nodes' rule-based fallbacks run. Nothing about the prompts or the parsing is re-implemented
here: the harness builds the `AgentState` those nodes read and measures what comes out.

Deployed configuration (the defaults for --live): model gpt-4o at the OpenAI-compatible endpoint
https://api.openai.com (`llm.get_chat_client` appends /v1), temperature 0.3 (hard-coded in
`get_chat_client`), 400 output tokens, and a 15 s per-call timeout enforced by the nodes' own
`asyncio.wait_for(..., settings.VLLM_TIMEOUT_SECONDS)`.

USAGE (from backend/)
---------------------
    python scripts/eval_llm_offline.py --generate-scenarios [--force]   # write the fixed set
    python scripts/eval_llm_offline.py --dry-run                        # fake client, no network
    OPENAI_API_KEY=sk-... python scripts/eval_llm_offline.py --live     # the real API

--live refuses to start unless OPENAI_API_KEY (or VLLM_API_KEY) is set in the PROCESS
environment. The key is never read from backend/.env, never printed and never written anywhere.
VLLM_ENDPOINT / VLLM_MODEL / VLLM_TIMEOUT_SECONDS / VLLM_MAX_TOKENS in the process environment,
or the --endpoint/--model/--timeout/--max-tokens flags, override the deployed defaults; the
effective values are printed before the first call and recorded in the results.

Outputs:
    eval_llm_offline_scenarios.json        the fixed, seeded scenario set (committed)
    eval_llm_offline_results.json          --live aggregate metrics (no raw text)
    eval_llm_offline_results_dryrun.json   --dry-run aggregate metrics (gitignored)
    eval_llm_offline_raw_<mode>.jsonl      per-run raw outputs (gitignored; written only after a
                                           secret scan finds nothing)

STUBS (everything that would otherwise need Postgres, Redis or the network)
-----
1. Section lookup (`content_context_service.build`, Postgres): replaced by the seeded course
   content built in memory by `app/db/course_content/*.build()`, rendered with the SAME
   `content_context_service._render_body`, so quiz/exercise masking is the deployed masking.
   Section ids are deterministic uuid5 values; lesson/module/course ids are None (they only feed
   research-event coordinates).
2. Learner activity (`learner_activity.attach`, Redis): the scenario's counters are placed on
   `content_context["learner_activity"]` directly, which is exactly what `attach` returns.
3. Learner profile and ladder rung (the profiler node, Postgres/Redis): the state carries
   `profile_service.default_profile()` with an affect history of the scenario's state, and
   `ladder_rung` is set to the scenario's rung, as the profiler would.
4. `state["db"] = None`: the content adapter's two DB lookups take their own documented degrade
   paths -- `_authored_variant` returns None (no designer-authored variant, so every generative
   action reaches the LLM; the seeded courses have none) and `_previously_shown` returns [] (no
   "already shown" history in the adapter prompt).
5. Research events (`research_logger.emit`, Redis): both nodes' `emit_research_event` is swapped
   for an in-memory capture for the duration of the run, then restored.
6. The LLM client: the process-wide singleton `llm._CLIENT` is replaced by a recording proxy
   around (live) the client `llm.get_chat_client()` builds from the patched settings, or
   (dry-run) the deterministic `FakeLLM`. The proxy times each call and keeps the raw response
   text, model snapshot and token usage; it never alters a request or a response.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import copy
import hashlib
import json
import math
import os
import random
import re
import sys
import time
import unicodedata
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

# `Settings` declares these with no default. Neither value is used: nothing here opens a database.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "script-only-not-a-real-secret")

from langchain_core.messages import AIMessage  # noqa: E402

from app.agents import fallbacks, llm  # noqa: E402
from app.agents.nodes import content_adapter, pedagogical  # noqa: E402
from app.agents.state import (  # noqa: E402
    AFFECT_SOURCE_FUSION,
    AFFECT_SOURCE_LEARNER_REQUEST,
    make_initial_state,
)
from app.core.config import settings  # noqa: E402
from app.db.course_content import building, foundations, java, multiagent  # noqa: E402
from app.services import content_context_service, profile_service  # noqa: E402

HARNESS_VERSION = 1

# ── scenario design ──────────────────────────────────────────────────────────────
SEED = 20260926
N_SCENARIOS = 60
RUNS_PER_SCENARIO = 3
STATES: tuple[str, ...] = ("confused", "bored")
ACTIVITY_PATTERNS: tuple[str, ...] = ("no_errors", "wrong_answers", "answer_revealed")
#: The warm-up course is excluded: it has no assessments, so there is nothing to leak, and the
#: "wrong answers" / "answer revealed" patterns presuppose a question in the section.
COURSES = (
    ("foundations", foundations.build),
    ("building", building.build),
    ("java", java.build),
    ("multiagent", multiagent.build),
)

# ── deployed LLM settings ────────────────────────────────────────────────────────
DEPLOYED: dict[str, Any] = {
    "endpoint": "https://api.openai.com",
    "model": "gpt-4o",
    "temperature": 0.3,
    "max_tokens": 400,
    "timeout_seconds": 15.0,
}
#: The dry-run's fake answers instantly, so a short budget only affects its scripted hang case,
#: which then exercises the real `asyncio.wait_for` timeout path in well under a second.
DRY_RUN_TIMEOUT_SECONDS = 0.2
DRY_RUN_ENDPOINT = "dry-run://fake-llm"

# ── metric parameters ────────────────────────────────────────────────────────────
WORD_LIMIT = 80  # content_adapter._SYSTEM_PROMPT: "keep it under 80 words"
SHORT_KEY_TOKENS = 3  # keyed answers with fewer normalized tokens are reported separately
NGRAM_N = 8  # near-verbatim overlap window for long keyed answers
WORD_BUCKETS = ((0, 0), (1, 20), (21, 40), (41, 60), (61, 80), (81, 100), (101, 150))

DEFAULT_SCENARIOS = SCRIPT_DIR / "eval_llm_offline_scenarios.json"
DEFAULT_RESULTS = {
    "live": SCRIPT_DIR / "eval_llm_offline_results.json",
    "dry-run": SCRIPT_DIR / "eval_llm_offline_results_dryrun.json",
}
DEFAULT_RAW = {
    "live": SCRIPT_DIR / "eval_llm_offline_raw_live.jsonl",
    "dry-run": SCRIPT_DIR / "eval_llm_offline_raw_dryrun.jsonl",
}

STUBS: tuple[str, ...] = (
    "content_context_service.build (Postgres) -> seeded course content built in memory, body "
    "rendered by the real content_context_service._render_body (same quiz/exercise masking); "
    "section_id = uuid5 of the section path; lesson/module/course ids None.",
    "learner_activity.attach (Redis) -> scenario counters placed on "
    "content_context['learner_activity'], the shape attach() returns.",
    "learner profiler (Postgres/Redis) -> profile_service.default_profile() with affect_history "
    "of the scenario state; ladder_rung set on the state from the scenario.",
    "state['db'] = None -> content_adapter._authored_variant returns None (LLM path always taken) "
    "and _previously_shown returns [] (no 'already shown' history in the adapter prompt).",
    "research_logger.emit (Redis) -> in-memory capture on both nodes' emit_research_event, "
    "restored after the run.",
    "llm._CLIENT singleton -> recording proxy around llm.get_chat_client() (live) or FakeLLM "
    "(dry-run); records latency, raw text, model snapshot, token usage; never alters traffic.",
)

DEFINITIONS: dict[str, str] = {
    "valid_json": (
        "Over pedagogical calls that returned a response: the node's own extraction "
        "(text from the first '{' to the last '}') json-parses to an object. "
        "valid_json_strict additionally requires the WHOLE stripped response to be that object "
        "(no prose, no code fences)."
    ),
    "in_vocabulary": (
        "Over valid-JSON responses: action_type is one of fallbacks.ACTION_TYPES. "
        "parse_accepted = pedagogical._parse_strategy(raw) is not None (the node's own verdict)."
    ),
    "fallback": (
        "strategy.fallback is True; fallback_reason is the node's own: timeout "
        "(asyncio.wait_for expired), vllm_error (client/API exception), parse_error (invalid JSON "
        "or out-of-vocabulary action_type)."
    ),
    "override": (
        "Over decisions where the model's choice was accepted (no fallback): the node set "
        "escalation_enforced. no_action_on_request = model_action_type == 'no_action' on a "
        "learner-request scenario (_honour_request); repeated_rung = any other enforced override, "
        "i.e. the model picked a ladder rung already spent (_enforce_escalation)."
    ),
    "ladder_adherence": (
        "The action is on fallbacks.ladder_actions(state) at an index >= the scenario's rung. "
        "'model' uses the model's own choice (model_action_type when overridden) over accepted "
        "decisions; 'final' uses the delivered action_type over all decisions."
    ),
    "no_action": "Share of decisions whose action_type is no_action ('model' and 'final' as above).",
    "word_count": (
        f"len(text.split()) on the adapter's final text (after its markdown strip); compliant "
        f"when <= {WORD_LIMIT}. Primary population: LLM-generated texts (metadata.generated)."
    ),
    "answer_leakage": (
        "Keyed answers of the bound section = text of every correct quiz option plus every "
        "non-empty exercise answer. A generated text LEAKS when any keyed answer appears in it "
        "either (exact) case-insensitively after NFKC, with word boundaries on alphanumeric ends, "
        "or (normalized) as a whole-token sequence after NFKC + casefold + every run of "
        "non-word characters -> one space. long_key / short_key split leaks by whether the "
        f"matched key has >= {SHORT_KEY_TOKENS} normalized tokens (short keys such as 'int' or "
        f"'9' can occur innocently; review them by hand). ngram{NGRAM_N} (secondary, not part "
        f"of 'any') = the text shares a {NGRAM_N}-token normalized shingle with a keyed answer "
        f"of >= {NGRAM_N} tokens. distractor_mention (informational) = same exact/normalized "
        "rule against the incorrect quiz options. key_not_in_section_body = a leak whose "
        "matched key the rendered section body (the model's context) does not itself contain "
        "under the same rule; a key the body states can be echoed without answering anything."
    ),
    "identical_text_repeat": (
        "LLM-generated texts grouped by (scenario, action_type) across runs, compared after "
        "content_adapter._normalise (lowercase, collapsed whitespace): identical pairs / pairs, "
        "and groups of >= 2 whose texts are all identical. distinct_text_ratio = unique "
        "normalized generated texts / generated texts, over the whole run."
    ),
    "latency": (
        "llm_call = wall time of client.ainvoke inside the node, for calls that returned; "
        "node = wall time of the whole node call (timeouts included). p50/p95 by linear "
        "interpolation."
    ),
    "model_snapshot": "response_metadata['model_name'] reported by the API on each response.",
}


# ═════════════════════════════════════════════════════════════════════════════════
# Scenarios
# ═════════════════════════════════════════════════════════════════════════════════


def _block_kind(block: Any) -> str:
    return getattr(block.block_type, "value", block.block_type)


def _assessment(blocks: list[Any]) -> tuple[list[str], list[str], list[str]]:
    """(questions, keyed answers, distractor options) of a section's assessment blocks."""
    questions: list[str] = []
    keyed: list[str] = []
    distractors: list[str] = []
    for block in sorted(blocks, key=lambda b: b.sort_order or 0):
        content = block.content if isinstance(block.content, dict) else {}
        kind = _block_kind(block)
        if kind == "quiz":
            questions.append(str(content.get("question") or ""))
            for option in content.get("options") or []:
                text = str(option.get("text") or "").strip()
                if text:
                    (keyed if option.get("isCorrect") else distractors).append(text)
        elif kind == "exercise":
            questions.append(str(content.get("prompt") or ""))
            answer = str(content.get("answer") or "").strip()
            if answer:  # a reflection has no keyed answer
                keyed.append(answer)
    return questions, keyed, distractors


def collect_sections() -> dict[str, dict[str, Any]]:
    """Every seeded section that has at least one keyed answer, keyed by its course path."""
    out: dict[str, dict[str, Any]] = {}
    for course_key, build in COURSES:
        course = build()
        for mi, mod in enumerate(course.modules, 1):
            for li, les in enumerate(mod.lessons, 1):
                for si, sec in enumerate(les.sections, 1):
                    blocks = list(sec.content_blocks or [])
                    questions, keyed, distractors = _assessment(blocks)
                    if not keyed:
                        continue
                    key = f"{course_key}/m{mi}/l{li}/s{si}"
                    out[key] = {
                        "section_key": key,
                        "section_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"affectlearn-eval/{key}")),
                        "course": course.title,
                        "module": mod.title,
                        "lesson": les.title,
                        "title": sec.title,
                        # Exactly what the deployed context carries: assessments masked.
                        "body": content_context_service._render_body(blocks),
                        "questions": questions,
                        "keyed_answers": keyed,
                        "distractor_options": distractors,
                    }
                    body = out[key]["body"]
                    out[key]["keyed_answers_in_body"] = [
                        a for a in keyed if detect_leak(body, [a])["leak"]
                    ]
    return out


def grid_cells() -> list[tuple[str, int, str, bool]]:
    """state x ladder rung x activity pattern x learner request (36 cells)."""
    return [
        (state, rung, pattern, requested)
        for state in STATES
        for rung in range(len(fallbacks.ladder_actions(state)))
        for pattern in ACTIVITY_PATTERNS
        for requested in (False, True)
    ]


def cell_key(state: str, rung: int, pattern: str, requested: bool) -> str:
    return f"{state}|r{rung}|{pattern}|{'request' if requested else 'detected'}"


def _activity(pattern: str, rng: random.Random) -> dict[str, Any]:
    if pattern == "no_errors":
        return {"quiz_incorrect_count": 0, "back_nav_count": 0, "show_answer_used": False,
                "time_on_section_s": float(rng.randint(40, 240))}
    if pattern == "wrong_answers":
        return {"quiz_incorrect_count": rng.choice((2, 3)), "back_nav_count": rng.choice((0, 1)),
                "show_answer_used": False, "time_on_section_s": float(rng.randint(90, 360))}
    return {"quiz_incorrect_count": 0, "back_nav_count": rng.choice((0, 1)),
            "show_answer_used": True, "time_on_section_s": float(rng.randint(90, 360))}


def generate_scenarios(seed: int = SEED, n: int = N_SCENARIOS) -> dict[str, Any]:
    """The fixed scenario set. Pure and deterministic for a given seed and course content.

    The full factorial grid has 36 cells (confused: 4 rungs, bored: 2 rungs; x 3 activity
    patterns x 2 request flags). The population sampled from is cells x eligible sections:
    every cell is taken once, the remaining n - 36 are distinct cells drawn with the seed for a
    second instance, and sections are dealt round-robin from a seeded shuffle so a repeated cell
    is always bound to a different section.
    """
    rng = random.Random(seed)
    sections = collect_sections()
    cells = grid_cells()
    rounds, remainder = divmod(n, len(cells))
    chosen = cells * rounds + rng.sample(cells, remainder)
    rng.shuffle(chosen)
    keys = sorted(sections)
    rng.shuffle(keys)

    used: dict[tuple, set[str]] = defaultdict(set)
    cursor = 0
    scenarios: list[dict[str, Any]] = []
    for idx, cell in enumerate(chosen):
        step = 0
        for step in range(len(keys)):
            key = keys[(cursor + step) % len(keys)]
            if key not in used[cell]:
                break
        cursor = (cursor + step + 1) % len(keys)
        used[cell].add(key)

        state, rung, pattern, requested = cell
        ladder = fallbacks.ladder_actions(state)
        profile = profile_service.default_profile()
        profile["affect_state"] = state
        profile["affect_history"] = [state] * min(5, rung + 2)
        scenarios.append({
            "scenario_id": f"S{idx + 1:02d}",
            "cell": cell_key(*cell),
            "affect_state": state,
            "ladder_rung": rung,
            "ladder": list(ladder),
            "rung_action": ladder[rung],
            "activity_pattern": pattern,
            "learner_activity": _activity(pattern, rng),
            "learner_request": requested,
            # A help request arrives with confidence 1.0 (ws._handle_help_request); a detected
            # state has passed the gate's 0.70 floor.
            "affect_source": AFFECT_SOURCE_LEARNER_REQUEST if requested else AFFECT_SOURCE_FUSION,
            "affect_confidence": 1.0 if requested else round(rng.uniform(0.72, 0.95), 2),
            "learner_profile": profile,
            "section_key": key,
        })

    used_keys = sorted({s["section_key"] for s in scenarios})
    return {
        "harness_version": HARNESS_VERSION,
        "generated_by": "backend/scripts/eval_llm_offline.py --generate-scenarios",
        "seed": seed,
        "n_scenarios": n,
        "runs_per_scenario": RUNS_PER_SCENARIO,
        "design": {
            "factors": {
                "affect_state": list(STATES),
                "ladder_rung": {s: list(fallbacks.ladder_actions(s)) for s in STATES},
                "activity_pattern": {
                    "no_errors": "0 wrong answers, answer not revealed, 40-240 s on section",
                    "wrong_answers": "2-3 wrong answers, answer not revealed, 90-360 s",
                    "answer_revealed": "0 wrong answers, answer revealed, 90-360 s",
                },
                "learner_request": [False, True],
            },
            "grid_cells": len(cells),
            "sampling": (
                f"all {len(cells)} cells once + {remainder} distinct cells drawn with the seed "
                "for a second instance (repeated cells bound to a different section); sections "
                "dealt round-robin from a seeded shuffle of the eligible pool"
            ),
            "eligible_sections": len(sections),
            "section_eligibility": (
                "seeded courses foundations/building/java/multiagent; section has at least one "
                "keyed answer (correct quiz option or non-empty exercise answer)"
            ),
        },
        "sections": {k: sections[k] for k in used_keys},
        "scenarios": scenarios,
    }


def dump_json(doc: Any) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def write_scenarios(doc: dict[str, Any], path: Path) -> str:
    """Write the scenario file and return its sha256."""
    data = dump_json(doc).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def subset(doc: dict[str, Any], scenario_ids: list[str] | None = None,
           limit: int | None = None) -> dict[str, Any]:
    """A copy of `doc` restricted to some scenarios (and only the sections they use)."""
    scenarios = doc["scenarios"]
    if scenario_ids is not None:
        wanted = set(scenario_ids)
        scenarios = [s for s in scenarios if s["scenario_id"] in wanted]
    if limit is not None:
        scenarios = scenarios[:limit]
    keys = {s["section_key"] for s in scenarios}
    return {**doc, "n_scenarios": len(scenarios), "scenarios": scenarios,
            "sections": {k: v for k, v in doc["sections"].items() if k in keys}}


def build_state(scenario: dict[str, Any], section: dict[str, Any], run: int) -> dict[str, Any]:
    """The AgentState the pedagogical node reads on a Phase B / adaptive cycle."""
    content_context = {
        "topic": section["title"],
        "lesson": section["lesson"],
        "body": section["body"],
        "difficulty": "unknown",  # no difficulty field exists on any content model
        "section_id": section["section_id"],
        "lesson_id": None,
        "module_id": None,
        "course_id": None,
        "learner_activity": dict(scenario["learner_activity"]),
    }
    state = make_initial_state(
        learner_id=f"eval-{scenario['scenario_id']}",
        session_id=f"eval-run-{run + 1}",
        cycle_number=run + 1,
        db=None,
        content_context=content_context,
        phase="phase_b",
        group="adaptive",
    )
    requested = bool(scenario["learner_request"])
    state.update({
        "affect_state": scenario["affect_state"],
        "affect_confidence": scenario["affect_confidence"],
        "affect_source": scenario["affect_source"],
        "detection_mode": None if requested else "multimodal",
        "learner_profile": copy.deepcopy(scenario["learner_profile"]),
        "ladder_rung": scenario["ladder_rung"],
        "should_adapt": True,
    })
    return state


# ═════════════════════════════════════════════════════════════════════════════════
# LLM clients
# ═════════════════════════════════════════════════════════════════════════════════


def _message_text(message: Any) -> str:
    return pedagogical._content_text(getattr(message, "content", message))


_ENCODER: Any = None


def estimate_tokens(text: str, use_tiktoken: bool = True) -> int:
    """o200k_base (the gpt-4o tokenizer) when tiktoken has it, else ~4 chars per token."""
    global _ENCODER
    if use_tiktoken:
        if _ENCODER is None:
            try:
                import tiktoken

                _ENCODER = tiktoken.get_encoding("o200k_base")
            except Exception:  # noqa: BLE001 -- an estimate is optional
                _ENCODER = False
        if _ENCODER:
            return len(_ENCODER.encode(text))
    return math.ceil(len(text) / 4)


class RecordingClient:
    """Stands in for the `ChatOpenAI` singleton; forwards every call unchanged and records it."""

    def __init__(self, inner: Any, use_tiktoken: bool = True) -> None:
        self.inner = inner
        self.use_tiktoken = use_tiktoken
        self.context: dict[str, Any] = {}
        self._pending: list[dict[str, Any]] = []

    def begin(self, context: dict[str, Any]) -> None:
        self.context = dict(context)
        self._pending = []
        if isinstance(self.inner, FakeLLM):
            self.inner.context = dict(context)

    def take(self) -> list[dict[str, Any]]:
        """The calls since `begin`. Prompt bookkeeping happens here, outside the node's timing."""
        calls, self._pending = self._pending, []
        for rec in calls:
            prompt = rec.pop("_prompt", "")
            rec["prompt_chars"] = len(prompt)
            rec["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
            rec["prompt_tokens_est"] = estimate_tokens(prompt, self.use_tiktoken)
        return calls

    async def ainvoke(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
        rec: dict[str, Any] = {
            "outcome": None,
            "_prompt": "\n".join(_message_text(m) for m in messages),
        }
        self._pending.append(rec)
        t0 = time.perf_counter()
        try:
            resp = await self.inner.ainvoke(messages, *args, **kwargs)
        except asyncio.CancelledError:
            rec["outcome"] = "cancelled"  # the node's wait_for expired
            raise
        except Exception as exc:
            # Type and HTTP status only: an API error message can echo request details.
            rec["outcome"] = "error"
            rec["error_type"] = type(exc).__name__
            rec["status_code"] = getattr(exc, "status_code", None)
            raise
        finally:
            rec["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        md = getattr(resp, "response_metadata", None) or {}
        usage = getattr(resp, "usage_metadata", None) or {}
        rec.update({
            "outcome": "response",
            "raw_text": _message_text(resp),
            "model_name": md.get("model_name"),
            "system_fingerprint": md.get("system_fingerprint"),
            "finish_reason": md.get("finish_reason"),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
        })
        return resp


_FIELD_CACHE: dict[str, re.Pattern[str]] = {}


def _prompt_field(name: str, text: str) -> str | None:
    pattern = _FIELD_CACHE.setdefault(name, re.compile(rf"^{re.escape(name)}: (.*)$", re.M))
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def _stable_int(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


class FakeLLM:
    """Deterministic stand-in for the chat model, used by --dry-run. No network.

    It recognises which node is calling by the system prompt it was sent (so it also proves the
    real prompt path ran) and answers from what the real human prompt says:

    * pedagogical: plausible JSON. With a stable per-(scenario, run) draw it takes the ladder rung
      it is shown, repeats the previous (already spent) rung, or -- on a learner request --
      answers no_action, so both code overrides get exercised.
    * content adapter: one fixed message naming the section topic.

    `script` pins special behaviours to (scenario_id, run, node):
    "hang" (never answers -> the node's own timeout), "invalid_json", "out_of_vocab", "fenced"
    (JSON inside a ```json fence), "leak" (fixed text + the section's first keyed answer),
    "overlong" (fixed text x4, > 80 words), "empty" (whitespace -> parse_error), or
    {"text": ...} for a literal response.
    """

    MODEL_NAME = "dry-run-fake"

    def __init__(self, script: dict[tuple, Any] | None = None, hang_seconds: float = 3600.0):
        self.script = dict(script or {})
        self.hang_seconds = hang_seconds
        self.context: dict[str, Any] = {}

    async def ainvoke(self, messages: Any, *args: Any, **kwargs: Any) -> AIMessage:
        system = _message_text(messages[0])
        human = _message_text(messages[-1])
        if system == pedagogical._SYSTEM_PROMPT:
            node = "pedagogical"
        elif system == content_adapter._SYSTEM_PROMPT:
            node = "content_adapter"
        else:
            raise RuntimeError("FakeLLM: unrecognised system prompt")
        ctx = self.context
        behaviour = self.script.get((ctx.get("scenario_id"), ctx.get("run"), node))
        if behaviour == "hang":
            await asyncio.sleep(self.hang_seconds)
        if isinstance(behaviour, dict) and "text" in behaviour:
            text = str(behaviour["text"])
        elif node == "pedagogical":
            text = self._strategy(human, ctx, behaviour)
        else:
            text = self._adaptation(human, ctx, behaviour)
        n_in = math.ceil((len(system) + len(human)) / 4)
        n_out = math.ceil(len(text) / 4)
        return AIMessage(
            content=text,
            response_metadata={"model_name": self.MODEL_NAME, "system_fingerprint": "fp_dry_run",
                               "finish_reason": "stop"},
            usage_metadata={"input_tokens": n_in, "output_tokens": n_out,
                            "total_tokens": n_in + n_out},
        )

    @staticmethod
    def _strategy(human: str, ctx: dict[str, Any], behaviour: Any) -> str:
        if behaviour == "invalid_json":
            return "The learner seems confused, so I would start with a gentle hint."
        if behaviour == "out_of_vocab":
            return json.dumps({"action_type": "give_quiz", "reason": "dry-run", "urgency": "low"})
        state = _prompt_field("affect_state", human) or "unknown"
        rung = int(_prompt_field("interventions_already_delivered", human) or 0)
        ladder = [a.strip() for a in (_prompt_field("escalation_ladder", human) or "").split("->")
                  if a.strip() and a.strip() in fallbacks.ACTION_TYPES]
        requested = "learner_requested: yes" in human
        draw = _stable_int(f"{ctx.get('scenario_id')}:{ctx.get('run')}") % 100
        if not ladder:
            action = "no_action"
        elif requested and draw < 30:
            action = "no_action"
        elif rung > 0 and draw < 60:
            action = ladder[min(rung, len(ladder)) - 1]
        else:
            action = ladder[min(rung, len(ladder) - 1)]
        payload: dict[str, Any] = {
            "action_type": action,
            "reason": f"dry-run policy for {state} at rung {rung}",
            "urgency": "medium",
        }
        if action == "show_video":
            topic = _prompt_field("content_topic", human) or "this idea"
            payload["video_brief"] = {"concept": topic[:60], "query": f"{topic[:60]} explained"}
        text = json.dumps(payload)
        return f"```json\n{text}\n```" if behaviour == "fenced" else text

    @staticmethod
    def _adaptation(human: str, ctx: dict[str, Any], behaviour: Any) -> str:
        if behaviour == "empty":
            return "   "
        topic = _prompt_field("content_topic", human) or "this section"
        text = (
            f"You're closer than you think. Look again at what the section says about {topic}, "
            "and try to put the key idea into one sentence of your own before moving on."
        )
        if behaviour == "leak" and ctx.get("keyed_answers"):
            text += f" In short: {ctx['keyed_answers'][0]}"
        if behaviour == "overlong":
            text = " ".join([text] * 4)
        return text


def default_dry_run_script(scenarios: list[dict[str, Any]]) -> dict[tuple, Any]:
    """Pin every non-default fake behaviour to the first four confused scenarios.

    Confused, because every rung of that ladder (and its fallback) is generative, so the
    adapter is guaranteed to call the LLM on those runs.
    """
    ids = [s["scenario_id"] for s in scenarios if s["affect_state"] == "confused"][:4]
    plan = (
        ("pedagogical", "invalid_json", 1),
        ("pedagogical", "hang", 2),
        ("pedagogical", "out_of_vocab", 0),
        ("pedagogical", "fenced", 0),
    )
    adapter = (("leak", 0), ("overlong", 0), ("hang", 1), ("empty", 2))
    script: dict[tuple, Any] = {}
    for sid, (node, behaviour, run), (ad_behaviour, ad_run) in zip(ids, plan, adapter):
        script[(sid, run, node)] = behaviour
        script[(sid, ad_run, "content_adapter")] = ad_behaviour
    return script


# ═════════════════════════════════════════════════════════════════════════════════
# Per-run metric helpers (pure)
# ═════════════════════════════════════════════════════════════════════════════════


def json_validity(text: str) -> tuple[bool, bool, dict[str, Any] | None]:
    """(strict, lenient, object). Lenient mirrors `_parse_strategy`'s brace extraction."""
    try:
        strict = isinstance(json.loads(text.strip()), dict)
    except (ValueError, TypeError):
        strict = False
    obj: Any = None
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
        except (ValueError, TypeError):
            obj = None
    lenient = isinstance(obj, dict)
    return strict, lenient, obj if lenient else None


def classify_override(strategy: dict[str, Any], requested: bool) -> str | None:
    """Which code override replaced the model's choice, if any."""
    if not strategy.get("escalation_enforced"):
        return None
    if requested and strategy.get("model_action_type") == "no_action":
        return "no_action_on_request"
    return "repeated_rung"


def ladder_adherent(action: str | None, affect_state: str, rung: int) -> bool:
    """`action` is on this state's ladder at or above the current rung (clamped)."""
    ladder = fallbacks.ladder_actions(affect_state)
    if not ladder or action not in ladder:
        return False
    return ladder.index(action) >= min(max(0, rung), len(ladder) - 1)


def word_count(text: Any) -> int:
    return len(str(text or "").split())


def _casefold(text: Any) -> str:
    return unicodedata.normalize("NFKC", str(text or "")).casefold()


def normalize_for_match(text: Any) -> str:
    return " ".join(re.sub(r"\W+", " ", _casefold(text)).split())


def _contains_exact(haystack: str, needle: str) -> bool:
    if not needle:
        return False
    pre = r"(?<!\w)" if re.match(r"\w", needle[0]) else ""
    post = r"(?!\w)" if re.match(r"\w", needle[-1]) else ""
    return re.search(pre + re.escape(needle) + post, haystack) is not None


def _shingles(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def _match(text_cf: str, text_norm: str, candidate: str) -> dict[str, bool]:
    cand_cf = _casefold(candidate).strip()
    cand_norm = normalize_for_match(candidate)
    return {
        "exact": _contains_exact(text_cf, cand_cf),
        "normalized": bool(cand_norm) and f" {cand_norm} " in f" {text_norm} ",
    }


def detect_leak(text: Any, keyed_answers: list[str],
                distractors: list[str] | tuple[str, ...] = (),
                body: str | None = None) -> dict[str, Any]:
    """Apply the documented leakage rule (see DEFINITIONS['answer_leakage']).

    With `body`, a matched key is also tested against the section body the model was shown:
    `leak_not_in_body` is a leak of a key the body does NOT state, which the model cannot have
    copied from its context and is the stronger evidence of answering the question.
    """
    text_cf = _casefold(text)
    text_norm = normalize_for_match(text)
    text_shingles = _shingles(text_norm.split(), NGRAM_N)
    out: dict[str, Any] = {
        "leak": False, "exact": False, "normalized": False, "long_key": False,
        "short_key": False, f"ngram{NGRAM_N}": False, "distractor_mention": False,
        "leak_not_in_body": False, "matched_keys": [], "matched_keys_in_body": [],
        "matched_distractors": [],
    }
    body_cf, body_norm = _casefold(body), normalize_for_match(body)
    for answer in keyed_answers:
        hit = _match(text_cf, text_norm, answer)
        tokens = normalize_for_match(answer).split()
        if hit["exact"] or hit["normalized"]:
            out["leak"] = True
            out["exact"] |= hit["exact"]
            out["normalized"] |= hit["normalized"]
            out["short_key" if len(tokens) < SHORT_KEY_TOKENS else "long_key"] = True
            out["matched_keys"].append(answer)
            in_body = body is not None and any(_match(body_cf, body_norm, answer).values())
            if in_body:
                out["matched_keys_in_body"].append(answer)
            else:
                out["leak_not_in_body"] = True
        if len(tokens) >= NGRAM_N and _shingles(tokens, NGRAM_N) & text_shingles:
            out[f"ngram{NGRAM_N}"] = True
    for option in distractors:
        hit = _match(text_cf, text_norm, option)
        if hit["exact"] or hit["normalized"]:
            out["distractor_mention"] = True
            out["matched_distractors"].append(option)
    return out


def evaluate_run(scenario: dict[str, Any], section: dict[str, Any], run: int,
                 strategy: dict[str, Any], ped_calls: list[dict[str, Any]], ped_ms: float,
                 adapter_update: dict[str, Any], ad_calls: list[dict[str, Any]],
                 ad_ms: float) -> dict[str, Any]:
    """One run's record: every per-run measurement the aggregates are computed from."""
    state, rung = scenario["affect_state"], int(scenario["ladder_rung"])
    requested = bool(scenario["learner_request"])

    call = ped_calls[0] if ped_calls else {}
    raw = call.get("raw_text") if call.get("outcome") == "response" else None
    strict = lenient = in_vocab = accepted = None
    json_action = None
    if raw is not None:
        strict, lenient, obj = json_validity(raw)
        json_action = obj.get("action_type") if obj else None
        in_vocab = bool(lenient and json_action in fallbacks.ACTION_TYPES)
        accepted = pedagogical._parse_strategy(raw) is not None
    fallback = bool(strategy.get("fallback"))
    model_action = None if fallback else strategy.get("model_action_type",
                                                      strategy.get("action_type"))
    ped = {
        "llm_called": bool(ped_calls),
        "llm_outcome": call.get("outcome"),
        "error_type": call.get("error_type"),
        "status_code": call.get("status_code"),
        "raw_text": raw,
        "json_strict": strict,
        "json_valid": lenient,
        "json_action_type": json_action,
        "in_vocabulary": in_vocab,
        "parse_accepted": accepted,
        "fallback": fallback,
        "fallback_reason": strategy.get("fallback_reason"),
        "model_action": model_action,
        "final_action": strategy.get("action_type"),
        "final_urgency": strategy.get("urgency"),
        "reason": strategy.get("reason"),
        "video_brief": strategy.get("video_brief"),
        "override": classify_override(strategy, requested),
        "ladder_adherent_model": None if fallback else ladder_adherent(model_action, state, rung),
        "ladder_adherent_final": ladder_adherent(strategy.get("action_type"), state, rung),
        "llm_latency_ms": call.get("latency_ms") if call.get("outcome") == "response" else None,
        "node_latency_ms": ped_ms,
        **{k: call.get(k) for k in ("model_name", "system_fingerprint", "finish_reason",
                                    "input_tokens", "output_tokens", "prompt_tokens_est",
                                    "prompt_chars", "prompt_sha256")},
    }

    content = (adapter_update or {}).get("adaptation_content")
    action = strategy.get("action_type")
    if not content:
        path = "no_content"
    elif action in fallbacks.SELECTIVE_ACTIONS:
        path = "selective"
    else:
        path = "generative"
    md = (content or {}).get("metadata") or {}
    text = (content or {}).get("text")
    generated = bool(md.get("generated"))
    acall = ad_calls[0] if ad_calls else {}
    adapter = {
        "action_type": action,
        "path": path,
        "llm_called": bool(ad_calls),
        "llm_outcome": acall.get("outcome"),
        "error_type": acall.get("error_type"),
        "status_code": acall.get("status_code"),
        "text": text,
        "generated": generated,
        "fallback": bool(md.get("fallback")),
        "fallback_reason": md.get("fallback_reason"),
        "word_count": word_count(text) if text is not None else None,
        "within_word_limit": (word_count(text) <= WORD_LIMIT) if text is not None else None,
        "leak": detect_leak(text, section["keyed_answers"], section["distractor_options"],
                            section["body"]) if generated else None,
        "llm_latency_ms": acall.get("latency_ms") if acall.get("outcome") == "response" else None,
        "node_latency_ms": ad_ms,
        **{k: acall.get(k) for k in ("model_name", "system_fingerprint", "finish_reason",
                                     "input_tokens", "output_tokens", "prompt_tokens_est",
                                     "prompt_chars", "prompt_sha256")},
    }
    return {
        "scenario_id": scenario["scenario_id"],
        "run": run,
        "cell": scenario["cell"],
        "affect_state": state,
        "ladder_rung": rung,
        "learner_request": requested,
        "activity_pattern": scenario["activity_pattern"],
        "section_key": scenario["section_key"],
        "pedagogical": ped,
        "content_adapter": adapter,
    }


# ═════════════════════════════════════════════════════════════════════════════════
# Aggregation (pure)
# ═════════════════════════════════════════════════════════════════════════════════


def rate(count: int, denominator: int) -> dict[str, Any]:
    return {"count": count, "denominator": denominator,
            "rate": round(count / denominator, 4) if denominator else None}


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    k = (len(xs) - 1) * q
    lo = math.floor(k)
    hi = min(lo + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 1)


def latency_summary(values: list[float | None]) -> dict[str, Any]:
    xs = [float(v) for v in values if v is not None]
    return {
        "n": len(xs),
        "p50_ms": percentile(xs, 0.50),
        "p95_ms": percentile(xs, 0.95),
        "mean_ms": round(sum(xs) / len(xs), 1) if xs else None,
        "max_ms": round(max(xs), 1) if xs else None,
    }


def word_distribution(counts: list[int]) -> dict[str, Any]:
    histogram: dict[str, int] = {}
    for lo, hi in WORD_BUCKETS:
        label = str(lo) if lo == hi else f"{lo}-{hi}"
        histogram[label] = sum(1 for c in counts if lo <= c <= hi)
    histogram[f"{WORD_BUCKETS[-1][1] + 1}+"] = sum(1 for c in counts if c > WORD_BUCKETS[-1][1])
    xs = sorted(counts)
    return {
        "compliant": rate(sum(1 for c in xs if c <= WORD_LIMIT), len(xs)),
        "limit": WORD_LIMIT,
        "min": xs[0] if xs else None,
        "p50": percentile(xs, 0.50),
        "p95": percentile(xs, 0.95),
        "max": xs[-1] if xs else None,
        "mean": round(sum(xs) / len(xs), 1) if xs else None,
        "histogram": histogram,
    }


def _counter(values: list[Any]) -> dict[str, int]:
    return dict(sorted(Counter(str(v) for v in values).items(), key=lambda kv: (-kv[1], kv[0])))


def _pedagogical_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    P = [r["pedagogical"] for r in records]
    responses = [p for p in P if p["llm_outcome"] == "response"]
    valid = [p for p in responses if p["json_valid"]]
    accepted = [p for p in P if not p["fallback"]]
    requested_accepted = [p for p, r in zip(P, records) if not p["fallback"] and r["learner_request"]]
    later_rung_accepted = [p for p, r in zip(P, records) if not p["fallback"] and r["ladder_rung"] > 0]

    by_cell: dict[str, dict[str, Any]] = {}
    for r in records:
        p = r["pedagogical"]
        key = f"{r['affect_state']}|r{r['ladder_rung']}"
        agg = by_cell.setdefault(key, {"n": 0, "fallback": 0, "override": 0,
                                       "model_adherent": 0, "model_decisions": 0,
                                       "final_adherent": 0, "final_actions": Counter()})
        agg["n"] += 1
        agg["fallback"] += int(p["fallback"])
        agg["override"] += int(p["override"] is not None)
        agg["final_adherent"] += int(bool(p["ladder_adherent_final"]))
        agg["final_actions"][p["final_action"]] += 1
        if not p["fallback"]:
            agg["model_decisions"] += 1
            agg["model_adherent"] += int(bool(p["ladder_adherent_model"]))
    for agg in by_cell.values():
        agg["final_actions"] = dict(agg["final_actions"].most_common())

    consistency = {
        # The harness's JSON/vocabulary split must agree with the node's own parser...
        "parse_accepted_vs_valid_and_in_vocab_mismatches": sum(
            1 for p in responses if p["parse_accepted"] != bool(p["json_valid"] and p["in_vocabulary"])
        ),
        # ...and with the node's decision to fall back.
        "parse_error_vs_not_accepted_mismatches": sum(
            1 for p in responses
            if (p["fallback_reason"] == "parse_error") != (not p["parse_accepted"])
        ),
    }
    return {
        "decisions": len(P),
        "llm_calls": sum(1 for p in P if p["llm_called"]),
        "llm_outcomes": _counter([p["llm_outcome"] for p in P]),
        "responses_received": len(responses),
        "valid_json": rate(len(valid), len(responses)),
        "valid_json_strict": rate(sum(1 for p in responses if p["json_strict"]), len(responses)),
        "valid_json_over_all_calls": rate(len(valid), sum(1 for p in P if p["llm_called"])),
        "in_vocabulary": rate(sum(1 for p in valid if p["in_vocabulary"]), len(valid)),
        "parse_accepted": rate(sum(1 for p in responses if p["parse_accepted"]), len(responses)),
        "out_of_vocabulary_actions": _counter(
            [p["json_action_type"] for p in valid if not p["in_vocabulary"]]
        ),
        "fallback": {
            **rate(sum(1 for p in P if p["fallback"]), len(P)),
            "by_reason": _counter([p["fallback_reason"] for p in P if p["fallback"]]),
        },
        "action_distribution": {
            "final": _counter([p["final_action"] for p in P]),
            "model": _counter([p["model_action"] for p in accepted]),
            "final_by_state": {
                state: _counter([r["pedagogical"]["final_action"] for r in records
                                 if r["affect_state"] == state])
                for state in sorted({r["affect_state"] for r in records})
            },
        },
        "no_action": {
            "final": rate(sum(1 for p in P if p["final_action"] == "no_action"), len(P)),
            "model": rate(sum(1 for p in accepted if p["model_action"] == "no_action"),
                          len(accepted)),
        },
        "override": {
            "any": rate(sum(1 for p in accepted if p["override"]), len(accepted)),
            "repeated_rung": rate(sum(1 for p in accepted if p["override"] == "repeated_rung"),
                                  len(accepted)),
            "no_action_on_request": rate(
                sum(1 for p in accepted if p["override"] == "no_action_on_request"), len(accepted)
            ),
            "repeated_rung_given_rung_above_0": rate(
                sum(1 for p in later_rung_accepted if p["override"] == "repeated_rung"),
                len(later_rung_accepted),
            ),
            "no_action_on_request_given_request": rate(
                sum(1 for p in requested_accepted if p["override"] == "no_action_on_request"),
                len(requested_accepted),
            ),
        },
        "ladder_adherence": {
            "model": rate(sum(1 for p in accepted if p["ladder_adherent_model"]), len(accepted)),
            "final": rate(sum(1 for p in P if p["ladder_adherent_final"]), len(P)),
            "by_state_rung": dict(sorted(by_cell.items())),
        },
        "video_brief_when_show_video": rate(
            sum(1 for p in accepted if p["model_action"] == "show_video" and p["video_brief"]),
            sum(1 for p in accepted if p["model_action"] == "show_video"),
        ),
        "latency": {
            "llm_call": latency_summary([p["llm_latency_ms"] for p in P]),
            "node": latency_summary([p["node_latency_ms"] for p in P]),
        },
        "consistency_checks": consistency,
    }


def _adapter_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    A = [r["content_adapter"] for r in records]
    generative = [a for a in A if a["path"] == "generative"]
    generated = [a for a in generative if a["generated"]]
    delivered = [a for a in A if a["text"]]
    leaks = [a["leak"] for a in generated]

    def leak_rate(flag: str) -> dict[str, Any]:
        return rate(sum(1 for lk in leaks if lk[flag]), len(leaks))

    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r, a in zip(records, A):
        if a["path"] == "generative" and a["generated"]:
            groups[(r["scenario_id"], a["action_type"])].append(content_adapter._normalise(a["text"]))
    pairs = identical = 0
    multi = all_same = 0
    for texts in groups.values():
        k = len(texts)
        if k < 2:
            continue
        multi += 1
        all_same += int(len(set(texts)) == 1)
        for i in range(k):
            for j in range(i + 1, k):
                pairs += 1
                identical += int(texts[i] == texts[j])
    all_texts = [t for texts in groups.values() for t in texts]

    return {
        "invocations": len(A),
        "paths": _counter([a["path"] for a in A]),
        "llm_calls": sum(1 for a in A if a["llm_called"]),
        "llm_outcomes": _counter([a["llm_outcome"] for a in A if a["llm_called"]]),
        "action_distribution_generative": _counter([a["action_type"] for a in generative]),
        "fallback": {
            **rate(sum(1 for a in generative if a["fallback"]), len(generative)),
            "by_reason": _counter([a["fallback_reason"] for a in generative if a["fallback"]]),
        },
        "generated_texts": len(generated),
        "word_count": {
            "generated": word_distribution([a["word_count"] for a in generated]),
            "all_delivered_texts": word_distribution([a["word_count"] for a in delivered]),
        },
        "answer_leakage": {
            "any": leak_rate("leak"),
            "exact": leak_rate("exact"),
            "normalized": leak_rate("normalized"),
            "long_key": leak_rate("long_key"),
            "short_key": leak_rate("short_key"),
            "key_not_in_section_body": leak_rate("leak_not_in_body"),
            f"ngram{NGRAM_N}": leak_rate(f"ngram{NGRAM_N}"),
            "distractor_mention": leak_rate("distractor_mention"),
            "leaks_by_scenario_run": sorted(
                f"{r['scenario_id']}#{r['run']}" for r, a in zip(records, A)
                if a["generated"] and a["leak"] and a["leak"]["leak"]
            ),
        },
        "identical_text_repeat": {
            "pairs": rate(identical, pairs),
            "groups_all_identical": rate(all_same, multi),
            "distinct_text_ratio": round(len(set(all_texts)) / len(all_texts), 4)
            if all_texts else None,
        },
        "latency": {
            "llm_call": latency_summary([a["llm_latency_ms"] for a in A]),
            "node": latency_summary([a["node_latency_ms"] for a in A if a["path"] != "no_content"]),
        },
    }


def _usage(records: list[dict[str, Any]], node: str) -> dict[str, Any]:
    rows = [r[node] for r in records if r[node]["llm_called"]]
    with_usage = [row for row in rows if row.get("input_tokens") is not None]
    return {
        "calls": len(rows),
        "calls_with_usage": len(with_usage),
        "input_tokens": sum(int(row["input_tokens"] or 0) for row in with_usage),
        "output_tokens": sum(int(row.get("output_tokens") or 0) for row in with_usage),
        "prompt_tokens_estimated": sum(int(row.get("prompt_tokens_est") or 0) for row in rows),
    }


def compute_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    names = [r[node]["model_name"] for r in records for node in ("pedagogical", "content_adapter")
             if r[node]["llm_outcome"] == "response" and r[node]["model_name"]]
    fps = [r[node]["system_fingerprint"] for r in records
           for node in ("pedagogical", "content_adapter")
           if r[node]["llm_outcome"] == "response" and r[node]["system_fingerprint"]]
    snapshots = Counter(names)
    return {
        "model_snapshot": snapshots.most_common(1)[0][0] if snapshots else None,
        "model_snapshots": dict(snapshots.most_common()),
        "system_fingerprints": dict(Counter(fps).most_common()),
        "n_runs_total": len(records),
        "token_usage": {"pedagogical": _usage(records, "pedagogical"),
                        "content_adapter": _usage(records, "content_adapter")},
        "pedagogical": _pedagogical_metrics(records),
        "content_adapter": _adapter_metrics(records),
    }


# ═════════════════════════════════════════════════════════════════════════════════
# Running
# ═════════════════════════════════════════════════════════════════════════════════


@contextlib.contextmanager
def patched_settings(**values: Any):
    saved = {k: getattr(settings, k) for k in values}
    try:
        for k, v in values.items():
            setattr(settings, k, v)
        yield
    finally:
        for k, v in saved.items():
            setattr(settings, k, v)


@contextlib.contextmanager
def captured_research_events():
    events: list[dict[str, Any]] = []

    async def _capture(event: dict[str, Any]) -> None:
        events.append(event)

    saved = (pedagogical.emit_research_event, content_adapter.emit_research_event)
    pedagogical.emit_research_event = _capture
    content_adapter.emit_research_event = _capture
    try:
        yield events
    finally:
        pedagogical.emit_research_event, content_adapter.emit_research_event = saved


def describe_client(client: Any) -> dict[str, Any]:
    retries = getattr(client, "max_retries", None)
    return {
        "base_url": str(getattr(client, "openai_api_base", "") or ""),
        "model": getattr(client, "model_name", None),
        "temperature": getattr(client, "temperature", None),
        "max_tokens": getattr(client, "max_tokens", None),
        "max_retries": retries if retries is not None else "openai SDK default (2)",
    }


def api_key_from_env() -> tuple[str | None, str | None]:
    """The key and the NAME of the variable it came from; process environment only."""
    for name in ("OPENAI_API_KEY", "VLLM_API_KEY"):
        value = (os.environ.get(name) or "").strip()
        if value and value != "not-needed":
            return value, name
    return None, None


def resolve_config(mode: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    o = {k: v for k, v in (overrides or {}).items() if v is not None}
    if mode == "live":
        env = os.environ
        return {
            "endpoint": o.get("endpoint") or env.get("VLLM_ENDPOINT") or DEPLOYED["endpoint"],
            "model": o.get("model") or env.get("VLLM_MODEL") or DEPLOYED["model"],
            "max_tokens": int(o.get("max_tokens") or env.get("VLLM_MAX_TOKENS")
                              or DEPLOYED["max_tokens"]),
            "timeout_seconds": float(o.get("timeout") or env.get("VLLM_TIMEOUT_SECONDS")
                                     or DEPLOYED["timeout_seconds"]),
        }
    return {
        "endpoint": DRY_RUN_ENDPOINT,
        "model": FakeLLM.MODEL_NAME,
        "max_tokens": DEPLOYED["max_tokens"],
        "timeout_seconds": float(o.get("timeout") or DRY_RUN_TIMEOUT_SECONDS),
    }


async def _run_all(doc: dict[str, Any], proxy: RecordingClient, runs: int) -> list[dict[str, Any]]:
    sections = doc["sections"]
    records: list[dict[str, Any]] = []
    # Run-major: every scenario once, then again. Spreads any drift in provider latency or
    # behaviour over the set instead of concentrating it on whichever scenarios came last.
    for run in range(runs):
        for scenario in doc["scenarios"]:
            section = sections[scenario["section_key"]]
            state = build_state(scenario, section, run)
            ctx = {"scenario_id": scenario["scenario_id"], "run": run,
                   "keyed_answers": section["keyed_answers"]}

            proxy.begin({**ctx, "node": "pedagogical"})
            t0 = time.perf_counter()
            update = await pedagogical.pedagogical_node(state)
            ped_ms = round((time.perf_counter() - t0) * 1000, 1)
            ped_calls = proxy.take()
            strategy = update["strategy"]

            proxy.begin({**ctx, "node": "content_adapter"})
            t0 = time.perf_counter()
            adapter_update = await content_adapter.content_adapter_node({**state, "strategy": strategy})
            ad_ms = round((time.perf_counter() - t0) * 1000, 1)
            ad_calls = proxy.take()

            records.append(evaluate_run(scenario, section, run, strategy, ped_calls, ped_ms,
                                        adapter_update, ad_calls, ad_ms))
    return records


async def evaluate(doc: dict[str, Any], *, mode: str, runs: int = RUNS_PER_SCENARIO,
                   api_key: str | None = None, key_source: str | None = None,
                   overrides: dict[str, Any] | None = None,
                   script: dict[tuple, Any] | None = None,
                   use_tiktoken: bool = True) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run every scenario `runs` times through both nodes; return (results, per-run records)."""
    if mode not in ("live", "dry-run"):
        raise ValueError(f"unknown mode {mode!r}")
    if mode == "live" and not api_key:
        raise RuntimeError("live mode needs an API key from the environment")
    cfg = resolve_config(mode, overrides)
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    saved_client = llm._CLIENT
    try:
        if mode == "dry-run":
            # Describe the client --live would send, built by the deployed code path. Building a
            # ChatOpenAI makes no network call; the placeholder key is never sent anywhere.
            with patched_settings(VLLM_ENDPOINT=DEPLOYED["endpoint"], VLLM_MODEL=DEPLOYED["model"],
                                  VLLM_MAX_TOKENS=DEPLOYED["max_tokens"],
                                  VLLM_API_KEY="dry-run-placeholder"):
                llm._reset()
                live_client = describe_client(llm.get_chat_client())
                llm._reset()
        with patched_settings(
            VLLM_ENDPOINT=cfg["endpoint"], VLLM_MODEL=cfg["model"],
            VLLM_MAX_TOKENS=cfg["max_tokens"], VLLM_TIMEOUT_SECONDS=cfg["timeout_seconds"],
            VLLM_API_KEY=api_key or "dry-run-placeholder",
        ), captured_research_events() as events:
            llm._reset()
            if mode == "live":
                inner: Any = llm.get_chat_client()
                client_desc = describe_client(inner)
            else:
                inner = FakeLLM(script if script is not None
                                else default_dry_run_script(doc["scenarios"]))
                client_desc = {"base_url": cfg["endpoint"], "model": FakeLLM.MODEL_NAME,
                               "temperature": None, "max_tokens": cfg["max_tokens"],
                               "max_retries": None}
            proxy = RecordingClient(inner, use_tiktoken=use_tiktoken)
            estimate_tokens("warm-up", use_tiktoken)  # load the encoder before anything is timed
            llm._CLIENT = proxy
            records = await _run_all(doc, proxy, runs)
    finally:
        llm._CLIENT = saved_client

    finished = datetime.now(timezone.utc)
    results = {
        "harness_version": HARNESS_VERSION,
        "mode": mode,
        "run_date": finished.date().isoformat(),
        "started_at_utc": started.isoformat(timespec="seconds"),
        "finished_at_utc": finished.isoformat(timespec="seconds"),
        "wall_seconds": round(time.perf_counter() - t0, 1),
        "config": {
            "effective": {**cfg, "temperature": client_desc.get("temperature"),
                          "client": client_desc},
            "deployed": dict(DEPLOYED),
            **({"live_client_as_built": live_client} if mode == "dry-run" else {}),
            "api_key_source": key_source if mode == "live" else None,
            "n_scenarios": len(doc["scenarios"]),
            "runs_per_scenario": runs,
            "seed": doc.get("seed"),
            "iteration_order": "run-major (all scenarios for run 1, then run 2, ...)",
            "research_events_captured": len(events),
        },
        **compute_metrics(records),
        "definitions": DEFINITIONS,
        "stubs": list(STUBS),
    }
    if mode == "dry-run":
        results["note"] = ("DRY RUN: every model response is from FakeLLM. These numbers test the "
                           "harness, not the model.")
    return results, records


# ═════════════════════════════════════════════════════════════════════════════════
# Output
# ═════════════════════════════════════════════════════════════════════════════════

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)api[_-]?key[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9._\-]{12,}"),
)


def find_secrets(blob: str, known: list[str | None] | tuple[str | None, ...] = ()) -> bool:
    if any(k and k in blob for k in known):
        return True
    return any(p.search(blob) for p in _SECRET_PATTERNS)


def summary_lines(results: dict[str, Any]) -> list[str]:
    p, a = results["pedagogical"], results["content_adapter"]

    def pct(block: dict[str, Any]) -> str:
        r = block.get("rate")
        return "n/a" if r is None else f"{100 * r:.1f}% ({block['count']}/{block['denominator']})"

    def ms(block: dict[str, Any]) -> str:
        if block["p50_ms"] is None:
            return "n/a"
        return f"p50={block['p50_ms']}ms p95={block['p95_ms']}ms"

    eff = results["config"]["effective"]
    return [
        f"mode={results['mode']}  date={results['run_date']}  model_snapshot="
        f"{results['model_snapshot']}  endpoint={eff['endpoint']}  timeout={eff['timeout_seconds']}s",
        f"scenarios={results['config']['n_scenarios']} x runs={results['config']['runs_per_scenario']}"
        f"  pedagogical calls={p['llm_calls']}  adapter calls={a['llm_calls']}",
        "PEDAGOGICAL",
        f"  valid JSON {pct(p['valid_json'])}  strict {pct(p['valid_json_strict'])}"
        f"  in-vocab {pct(p['in_vocabulary'])}",
        f"  fallback {pct(p['fallback'])} by reason {p['fallback']['by_reason']}",
        f"  no_action final {pct(p['no_action']['final'])}  model {pct(p['no_action']['model'])}",
        f"  override any {pct(p['override']['any'])}  repeated_rung "
        f"{pct(p['override']['repeated_rung'])}  no_action_on_request "
        f"{pct(p['override']['no_action_on_request'])}",
        f"  ladder adherence model {pct(p['ladder_adherence']['model'])}  final "
        f"{pct(p['ladder_adherence']['final'])}",
        f"  actions final {p['action_distribution']['final']}",
        f"  latency llm {ms(p['latency']['llm_call'])}  node {ms(p['latency']['node'])}",
        "CONTENT ADAPTER",
        f"  paths {a['paths']}  fallback {pct(a['fallback'])} by reason {a['fallback']['by_reason']}",
        f"  words<= {WORD_LIMIT} {pct(a['word_count']['generated']['compliant'])}  p50="
        f"{a['word_count']['generated']['p50']} p95={a['word_count']['generated']['p95']} "
        f"max={a['word_count']['generated']['max']}",
        f"  answer leak {pct(a['answer_leakage']['any'])}  long-key "
        f"{pct(a['answer_leakage']['long_key'])}  short-key {pct(a['answer_leakage']['short_key'])}"
        f"  ngram{NGRAM_N} {pct(a['answer_leakage'][f'ngram{NGRAM_N}'])}",
        f"  identical repeat pairs {pct(a['identical_text_repeat']['pairs'])}  distinct ratio "
        f"{a['identical_text_repeat']['distinct_text_ratio']}",
        f"  latency llm {ms(a['latency']['llm_call'])}  node {ms(a['latency']['node'])}",
        f"tokens {results['token_usage']}",
    ]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline evaluation of the Pedagogical Agent and Content Adapter LLM nodes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="deterministic fake LLM, no network")
    mode.add_argument("--live", action="store_true",
                      help="real API; needs OPENAI_API_KEY (or VLLM_API_KEY) in the environment")
    mode.add_argument("--generate-scenarios", action="store_true",
                      help="write the fixed scenario set and exit")
    parser.add_argument("--force", action="store_true",
                        help="with --generate-scenarios: overwrite an existing file")
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--runs", type=int, default=RUNS_PER_SCENARIO)
    parser.add_argument("--limit", type=int, default=None, help="only the first N scenarios")
    parser.add_argument("--out", type=Path, default=None, help="aggregate results JSON path")
    parser.add_argument("--raw-out", type=Path, default=None, help="per-run raw JSONL path")
    parser.add_argument("--no-raw", action="store_true", help="do not write per-run raw outputs")
    parser.add_argument("--endpoint", default=None, help=f"live only (default {DEPLOYED['endpoint']})")
    parser.add_argument("--model", default=None, help=f"live only (default {DEPLOYED['model']})")
    parser.add_argument("--timeout", type=float, default=None, help="per-call timeout seconds")
    parser.add_argument("--max-tokens", type=int, default=None, help="live only (default 400)")
    parser.add_argument("--no-tiktoken", action="store_true",
                        help="estimate prompt tokens as chars/4 instead of o200k_base")
    parser.add_argument("--verbose", action="store_true", help="keep the nodes' info logs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.generate_scenarios:
        if args.scenarios.exists() and not args.force:
            print(f"{args.scenarios} exists; pass --force to overwrite it.", file=sys.stderr)
            return 1
        doc = generate_scenarios()
        digest = write_scenarios(doc, args.scenarios)
        print(f"wrote {len(doc['scenarios'])} scenarios over {len(doc['sections'])} sections to "
              f"{args.scenarios} (sha256 {digest[:12]})")
        return 0

    mode = "live" if args.live else "dry-run"
    api_key, key_source = (None, None)
    if mode == "live":
        api_key, key_source = api_key_from_env()
        if not api_key:
            print("REFUSING --live: set OPENAI_API_KEY (or VLLM_API_KEY) in the environment of "
                  "this process. It is not read from backend/.env. No request was made.",
                  file=sys.stderr)
            return 2

    # The fixed set exists on disk before any run; a run always reads it back from the file.
    if not args.scenarios.exists():
        digest = write_scenarios(generate_scenarios(), args.scenarios)
        print(f"generated the scenario set first: {args.scenarios} (sha256 {digest[:12]})")
    data = args.scenarios.read_bytes()
    doc = json.loads(data)
    if args.limit is not None:
        doc = subset(doc, limit=args.limit)

    cfg = resolve_config(mode, {"endpoint": args.endpoint, "model": args.model,
                                "timeout": args.timeout, "max_tokens": args.max_tokens})
    print(f"[{mode}] endpoint={cfg['endpoint']} model={cfg['model']} max_tokens="
          f"{cfg['max_tokens']} timeout={cfg['timeout_seconds']}s key_source={key_source} "
          f"scenarios={len(doc['scenarios'])} runs={args.runs} -> up to "
          f"{2 * len(doc['scenarios']) * args.runs} LLM calls")

    results, records = asyncio.run(evaluate(
        doc, mode=mode, runs=args.runs, api_key=api_key, key_source=key_source,
        overrides={"endpoint": args.endpoint, "model": args.model, "timeout": args.timeout,
                   "max_tokens": args.max_tokens},
        use_tiktoken=not args.no_tiktoken,
    ))
    try:
        scenario_file = str(args.scenarios.resolve().relative_to(BACKEND_DIR.parent))
    except ValueError:
        scenario_file = str(args.scenarios)
    results["config"]["scenario_file"] = scenario_file.replace("\\", "/")
    results["config"]["scenario_sha256"] = hashlib.sha256(data).hexdigest()
    results["config"]["limit"] = args.limit

    raw_path = args.raw_out or DEFAULT_RAW[mode]
    raw_info: dict[str, Any] = {"written": False, "path": None, "reason": None}
    if args.no_raw:
        raw_info["reason"] = "--no-raw"
    else:
        blob = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
        if find_secrets(blob, [api_key]):
            raw_info["reason"] = "secret-like string detected in raw outputs; not written"
        else:
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(blob, encoding="utf-8")
            raw_info.update(written=True, path=raw_path.name, records=len(records))
    results["raw_output"] = raw_info

    out_path = args.out or DEFAULT_RESULTS[mode]
    text = dump_json(results)
    if find_secrets(text, [api_key]):
        print("REFUSING to write results: a secret-like string was found in them.", file=sys.stderr)
        return 3
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")

    for line in summary_lines(results):
        print(line)
    print(f"results -> {out_path}")
    if raw_info["written"]:
        print(f"raw     -> {raw_path}")
    elif raw_info["reason"]:
        print(f"raw     -> not written ({raw_info['reason']})")
    return 0


def _quiet_logs() -> None:
    """Drop the nodes' per-call info logs; warnings (timeouts, parse errors) still print."""
    import logging

    import structlog

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))


if __name__ == "__main__":
    if "--verbose" not in sys.argv[1:]:
        _quiet_logs()
    raise SystemExit(main())
