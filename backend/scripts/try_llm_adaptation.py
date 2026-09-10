"""Ask a real LLM for real adaptations, and print what a learner would see.

WHY THIS EXISTS
---------------
`VLLM_ENDPOINT` defaults to `http://vllm:8080`, a docker-compose service name that does not
resolve on App Service, and the subscription carries no GPU quota — so in the deployed system
every strategy and content call times out and falls back to `fallbacks.rule_based_content`
(`services/llm_health.py` says so outright). The generative half of the pedagogical loop has
therefore never been observed against an actual model on this deployment.

That is not the same as it being broken. The prompts are built, the parsing and validation are
built, the fallback is built and tested. What was missing was a way to point the whole thing at
any OpenAI-compatible endpoint and look at the output.

WHAT IT EXERCISES
-----------------
The real prompt builders and the real nodes, nothing mocked:

    content_context + affect  ->  pedagogical_node   -> {action_type, reason, urgency}
                              ->  content_adapter_node -> the learner-visible message
                              ->  deliver_node        -> the WebSocket payload

USAGE
-----
Any OpenAI-compatible server works; it does not have to be vLLM on a GPU.

    # Ollama (free, local, no key)
    ollama serve
    ollama pull llama3.1:8b
    VLLM_ENDPOINT=http://localhost:11434 \
    VLLM_MODEL=llama3.1:8b \
    VLLM_API_KEY=ollama \
    VLLM_TIMEOUT_SECONDS=60 \
    python scripts/try_llm_adaptation.py

    # Groq / OpenAI / Together / anything OpenAI-compatible
    VLLM_ENDPOINT=https://api.groq.com/openai \
    VLLM_MODEL=llama-3.1-8b-instant \
    VLLM_API_KEY=$YOUR_KEY \
    python scripts/try_llm_adaptation.py

RAISE THE TIMEOUT FOR LOCAL MODELS
----------------------------------
`VLLM_TIMEOUT_SECONDS` defaults to 3.0, which is the right production budget (the loop has a
200ms-per-cycle target and a learner must not wait). A model running on CPU will not answer in
three seconds, so leaving the default here makes every call fall back and the output looks
identical to having no model at all — which is exactly the wrong conclusion to draw. Raise it for
this script; do not raise it in production.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "script-only-not-a-real-secret")

from app.agents.nodes.content_adapter import content_adapter_node  # noqa: E402
from app.agents.nodes.pedagogical import pedagogical_node  # noqa: E402
from app.agents.nodes.terminal import deliver_node  # noqa: E402
from app.agents.state import make_initial_state  # noqa: E402
from app.core.config import settings  # noqa: E402

#: A section with enough substance that a vague answer is visibly vague.
SECTION = {
    "section_id": "script-section",
    "topic": "TCP three-way handshake",
    "lesson": "Establishing a connection",
    "difficulty": "unknown",
    "body": (
        "TCP opens a connection with a three-way handshake. The client sends a SYN carrying its "
        "initial sequence number. The server replies with SYN-ACK, acknowledging the client's "
        "number and sending its own. The client answers with ACK. Only then does data flow. "
        "The third packet exists so the server learns that the client received its reply; "
        "without it the server would have to commit resources to a connection that may never "
        "have been requested by a real client."
    ),
}

#: `rung` is how many interventions were already delivered for this state in this section, and the
#: rule ladder escalates with it. Included so the escalation is visible: a learner confused three
#: times should not receive the same intervention three times.
SCENARIOS = [
    ("confused", 0, "first sign of confusion"),
    ("confused", 1, "still confused after a hint"),
    ("confused", 2, "hint and breakdown both failed"),
    ("bored", 0, "under-challenged"),
    ("frustrated", 0, "struggling and losing patience"),
]


def build_state(affect: str, rung: int, profile_skill: str) -> dict:
    state = make_initial_state(
        learner_id="script-learner",
        session_id="script-session",
        cycle_number=9,
        phase="phase_b",
        group="adaptive",
    )
    state["affect_state"] = affect
    state["affect_confidence"] = 0.91
    state["affect_source"] = "behavioral_model"
    state["detection_mode"] = "behavioral_only"
    state["learner_profile"] = {
        "skill_level": profile_skill,
        "affect_history": [affect, affect],
    }
    state["content_context"] = SECTION
    # Set directly: this script is about the GENERATIVE half, so it does not re-derive the gate.
    # `scripts/replay_session.py` is the tool for exercising the gate against real event streams.
    state["should_adapt"] = True
    state["ladder_rung"] = rung
    return state


async def run_one(affect: str, rung: int, note: str, skill: str) -> None:
    state = build_state(affect, rung, skill)

    state.update(await pedagogical_node(state))
    strategy = state.get("strategy") or {}

    state.update(await content_adapter_node(state))
    content = state.get("adaptation_content") or {}

    state.update(await deliver_node(state))
    message = state.get("delivery_message")

    md = content.get("metadata") or {}
    print(f"\n  {affect.upper()}  rung {rung}  ({note})")
    print(f"    decision   : {strategy.get('action_type')}   urgency={strategy.get('urgency')}")
    print(f"    reason     : {strategy.get('reason') or '(none given)'}")

    if strategy.get("fallback"):
        print("    !! the STRATEGY came from the rule ladder, not the model")
    if md.get("fallback"):
        print(f"    !! the CONTENT came from canned copy, not the model "
              f"(reason: {md.get('fallback_reason')})")
    if md.get("authored_variant"):
        print("    (served a designer-authored variant; the model was not asked)")

    if not message:
        print("    delivered  : nothing")
        return
    print(f"    delivered  : {message['content']['text']}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skill",
        default="intermediate",
        choices=["beginner", "intermediate", "advanced"],
        help="Learner skill level put in the prompt. Worth varying — the same section should "
             "not produce the same message for a beginner and an expert.",
    )
    args = parser.parse_args()

    print("=" * 92)
    print(f"endpoint : {settings.VLLM_ENDPOINT.rstrip('/')}/v1")
    print(f"model    : {settings.VLLM_MODEL}")
    print(f"timeout  : {settings.VLLM_TIMEOUT_SECONDS}s")
    print(f"skill    : {args.skill}")
    print("=" * 92)
    if settings.VLLM_TIMEOUT_SECONDS <= 5 and "localhost" in settings.VLLM_ENDPOINT:
        print("\n  NOTE: a local model will almost certainly exceed a "
              f"{settings.VLLM_TIMEOUT_SECONDS}s timeout, and every")
        print("  line below will then say the content came from canned copy. Set")
        print("  VLLM_TIMEOUT_SECONDS=60 for this script if that happens.\n")

    print("\nSection the learner is reading:")
    print("  " + SECTION["body"][:150] + "...")

    for affect, rung, note in SCENARIOS:
        await run_one(affect, rung, note, args.skill)

    print("\n" + "=" * 92)
    print("Any line marked !! did not come from the model. If every line is marked, the endpoint")
    print("is unreachable or too slow — check the URL and raise VLLM_TIMEOUT_SECONDS.")
    print("=" * 92)


if __name__ == "__main__":
    asyncio.run(main())
