"""Tests for the offline LLM evaluation harness (`scripts/eval_llm_offline.py`).

No network anywhere: every run uses the harness's deterministic `FakeLLM` (its --dry-run client),
either with its default script or with responses pinned per test, so each metric can be checked
against a run whose outcome is known in advance. The nodes themselves are real.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

import app.agents.llm as llm_mod
import app.agents.nodes.pedagogical as ped_mod
from app.agents import fallbacks
from app.core.config import settings

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval_llm_offline.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location("eval_llm_offline", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ev = _load_harness()


@pytest.fixture(scope="module")
def doc():
    return ev.generate_scenarios()


def _small_doc(doc):
    """Four confused scenarios (where the default fake script pins its special cases) + two bored."""
    confused = [s["scenario_id"] for s in doc["scenarios"] if s["affect_state"] == "confused"][:4]
    bored = [s["scenario_id"] for s in doc["scenarios"] if s["affect_state"] == "bored"][:2]
    return ev.subset(doc, scenario_ids=confused + bored), confused


def _scenario(doc, sid, state, rung, requested):
    base = copy.deepcopy(next(s for s in doc["scenarios"] if s["affect_state"] == state))
    base.update(
        scenario_id=sid,
        ladder_rung=rung,
        rung_action=fallbacks.ladder_actions(state)[rung],
        learner_request=requested,
        affect_source="learner_request" if requested else "fusion",
        affect_confidence=1.0 if requested else 0.8,
        cell=ev.cell_key(state, rung, base["activity_pattern"], requested),
    )
    return base


def _strategy_json(action):
    return {"text": json.dumps({"action_type": action, "reason": "test", "urgency": "low"})}


# ── scenarios ────────────────────────────────────────────────────────────────────


def test_scenarios_are_deterministic_and_cover_the_grid(doc):
    assert ev.dump_json(ev.generate_scenarios()) == ev.dump_json(doc)
    assert ev.dump_json(ev.generate_scenarios(seed=1)) != ev.dump_json(doc)

    scenarios = doc["scenarios"]
    assert len(scenarios) == ev.N_SCENARIOS == 60
    assert len({s["scenario_id"] for s in scenarios}) == 60

    cells = Counter(s["cell"] for s in scenarios)
    assert len(cells) == len(ev.grid_cells()) == 36  # every cell present
    assert set(cells.values()) == {1, 2}

    sections_by_cell = defaultdict(list)
    for s in scenarios:
        sections_by_cell[s["cell"]].append(s["section_key"])
    assert all(len(set(v)) == len(v) for v in sections_by_cell.values())

    for s in scenarios:
        section = doc["sections"][s["section_key"]]
        assert section["keyed_answers"], s["scenario_id"]
        assert s["rung_action"] == fallbacks.ladder_actions(s["affect_state"])[s["ladder_rung"]]
        assert (s["affect_source"] == "learner_request") is s["learner_request"]
        # The body is the deployed, masked rendering: no assessment wording reaches it.
        for question in section["questions"]:
            assert not question or question not in section["body"]


def test_committed_scenario_file_is_a_complete_fixed_set():
    committed = json.loads(ev.DEFAULT_SCENARIOS.read_text(encoding="utf-8"))
    assert committed["seed"] == ev.SEED
    assert len(committed["scenarios"]) == committed["n_scenarios"] == 60
    assert all(s["section_key"] in committed["sections"] for s in committed["scenarios"])


# ── per-run metric rules ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, strict, lenient",
    [
        ('{"action_type": "show_hint", "reason": "r", "urgency": "low"}', True, True),
        ('```json\n{"action_type": "show_hint"}\n```', False, True),
        ('Sure: {"action_type": "show_hint"} hope that helps', False, True),
        ("I would give the learner a hint.", False, False),
        ('{"action_type": "show_hint",', False, False),
        ("[1, 2]", False, False),
    ],
)
def test_json_validity(text, strict, lenient):
    got_strict, got_lenient, obj = ev.json_validity(text)
    assert (got_strict, got_lenient) == (strict, lenient)
    assert (obj is not None) is lenient
    # Lenient validity is exactly the node's own extraction.
    if lenient:
        assert (ped_mod._parse_strategy(text) is not None) is True


def test_leak_detection_rules():
    long_key = ("It pursues a goal and adapts its actions to the current situation, rather "
                "than following a fixed script.")
    keys = [long_key, "int"]
    distractors = ["It uses a large language model internally."]

    normalized = ev.detect_leak(
        "Remember: it PURSUES a goal -- and adapts its actions to the current situation; "
        "rather than following a fixed script!", keys, distractors)
    assert normalized["leak"] and normalized["normalized"] and not normalized["exact"]
    assert normalized["long_key"] and not normalized["short_key"]

    exact = ev.detect_leak(f"In short: {long_key.upper()}", keys)
    assert exact["leak"] and exact["exact"]

    # Short keys are word-bounded (no match inside "point") and reported separately.
    assert not ev.detect_leak("Point at the type you need.", keys)["leak"]
    short = ev.detect_leak("Use an INT here.", keys)
    assert short["leak"] and short["short_key"] and not short["long_key"]
    assert ev.detect_leak("Try .equals() instead.", [".equals()"])["exact"]

    # A distractor is not the answer.
    wrong = ev.detect_leak("It uses a large language model internally, but so what?", keys,
                           distractors)
    assert not wrong["leak"] and wrong["distractor_mention"]

    # Near-verbatim partial quote of a long key: secondary flag only.
    partial = ev.detect_leak("It adapts its actions to the current situation rather quickly.", keys)
    assert partial[f"ngram{ev.NGRAM_N}"] and not partial["leak"]

    # Body-aware: echoing a key the section itself states is separated out.
    echoed = ev.detect_leak("Use an int here.", ["int"], body="An int holds whole numbers.")
    assert echoed["leak"] and not echoed["leak_not_in_body"]
    assert echoed["matched_keys_in_body"] == ["int"]
    assert ev.detect_leak("Use an int here.", ["int"], body="Whole numbers.")["leak_not_in_body"]


def test_word_count_and_compliance():
    assert ev.word_count("one two  three\nfour") == 4
    assert ev.word_count("") == 0 and ev.word_count(None) == 0
    eighty = " ".join(["w"] * 80)
    assert ev.word_count(eighty) == 80 and ev.word_count(eighty + " x") == 81

    dist = ev.word_distribution([80, 81, 10, 0])
    assert dist["compliant"] == {"count": 3, "denominator": 4, "rate": 0.75}
    assert dist["histogram"]["0"] == 1
    assert dist["histogram"]["61-80"] == 1 and dist["histogram"]["81-100"] == 1
    assert dist["max"] == 81


def test_override_classification():
    assert ev.classify_override({"action_type": "show_hint"}, True) is None
    assert ev.classify_override(
        {"escalation_enforced": True, "model_action_type": "no_action"}, True
    ) == "no_action_on_request"
    assert ev.classify_override(
        {"escalation_enforced": True, "model_action_type": "show_hint"}, False
    ) == "repeated_rung"
    assert ev.ladder_adherent("show_alternative", "confused", 2)
    assert not ev.ladder_adherent("show_hint", "confused", 2)
    assert not ev.ladder_adherent("no_action", "bored", 0)


# ── through the real nodes ───────────────────────────────────────────────────────


async def test_override_detection_through_the_real_node(doc):
    scenarios = [
        _scenario(doc, "T1", "confused", 2, False),  # repeats a spent rung
        _scenario(doc, "T2", "confused", 0, True),   # no_action on a learner request
        _scenario(doc, "T3", "confused", 1, False),  # no_action on a detection: allowed
        _scenario(doc, "T4", "bored", 0, False),     # on the ladder: untouched
    ]
    script = {
        ("T1", 0, "pedagogical"): _strategy_json("show_hint"),
        ("T2", 0, "pedagogical"): _strategy_json("no_action"),
        ("T3", 0, "pedagogical"): _strategy_json("no_action"),
        ("T4", 0, "pedagogical"): _strategy_json("increase_difficulty"),
    }
    results, records = await ev.evaluate(
        {**doc, "scenarios": scenarios}, mode="dry-run", runs=1, script=script, use_tiktoken=False
    )
    by_id = {r["scenario_id"]: r for r in records}
    t1, t2, t3, t4 = (by_id[k]["pedagogical"] for k in ("T1", "T2", "T3", "T4"))

    assert t1["override"] == "repeated_rung"
    assert (t1["model_action"], t1["final_action"]) == ("show_hint", "show_alternative")
    assert t1["ladder_adherent_model"] is False and t1["ladder_adherent_final"] is True
    assert t2["override"] == "no_action_on_request" and t2["final_action"] == "show_hint"
    assert t3["override"] is None and t3["final_action"] == "no_action"
    assert by_id["T3"]["content_adapter"]["path"] == "no_content"
    assert t4["override"] is None and t4["ladder_adherent_model"] is True

    p = results["pedagogical"]
    assert p["override"]["any"]["count"] == 2 and p["override"]["any"]["denominator"] == 4
    assert p["override"]["repeated_rung"]["count"] == 1
    assert p["override"]["no_action_on_request"]["count"] == 1
    assert p["override"]["repeated_rung_given_rung_above_0"] == {
        "count": 1, "denominator": 2, "rate": 0.5}
    assert p["override"]["no_action_on_request_given_request"]["rate"] == 1.0
    assert p["no_action"]["model"]["count"] == 2 and p["no_action"]["final"]["count"] == 1
    assert p["ladder_adherence"]["model"]["count"] == 1
    assert p["ladder_adherence"]["final"]["count"] == 3


async def test_valid_json_and_vocabulary_counting(doc):
    ids = [s["scenario_id"] for s in doc["scenarios"] if s["affect_state"] == "confused"][:4]
    small = ev.subset(doc, scenario_ids=ids)
    script = {
        (ids[0], 0, "pedagogical"): _strategy_json("show_video"),
        (ids[1], 0, "pedagogical"): "fenced",
        (ids[2], 0, "pedagogical"): "out_of_vocab",
        (ids[3], 0, "pedagogical"): "invalid_json",
    }
    results, _ = await ev.evaluate(small, mode="dry-run", runs=1, script=script,
                                   use_tiktoken=False)
    p = results["pedagogical"]
    assert p["responses_received"] == 4
    assert p["valid_json"]["count"] == 3          # all but the prose answer
    assert p["valid_json_strict"]["count"] == 2   # the fence fails the strict test
    assert p["in_vocabulary"] == {"count": 2, "denominator": 3, "rate": 0.6667}
    assert p["parse_accepted"]["count"] == 2
    assert p["out_of_vocabulary_actions"] == {"give_quiz": 1}
    assert p["fallback"]["by_reason"] == {"parse_error": 2}
    assert set(p["consistency_checks"].values()) == {0}


def test_dry_run_cli_end_to_end(doc, tmp_path):
    small, confused = _small_doc(doc)
    scenario_file = tmp_path / "scenarios.json"
    ev.write_scenarios(small, scenario_file)
    out, raw = tmp_path / "results.json", tmp_path / "raw.jsonl"
    before = (llm_mod._CLIENT, settings.VLLM_TIMEOUT_SECONDS, settings.VLLM_ENDPOINT,
              ped_mod.emit_research_event)

    rc = ev.main(["--dry-run", "--scenarios", str(scenario_file), "--out", str(out),
                  "--raw-out", str(raw), "--no-tiktoken"])
    assert rc == 0

    # Every global the run swaps is back as it was.
    assert (llm_mod._CLIENT, settings.VLLM_TIMEOUT_SECONDS, settings.VLLM_ENDPOINT,
            ped_mod.emit_research_event) == before

    results = json.loads(out.read_text(encoding="utf-8"))
    p, a = results["pedagogical"], results["content_adapter"]
    assert results["mode"] == "dry-run" and results["model_snapshot"] == "dry-run-fake"
    assert results["run_date"]
    assert results["config"]["live_client_as_built"]["base_url"] == "https://api.openai.com/v1"
    assert results["config"]["live_client_as_built"]["temperature"] == 0.3
    assert results["config"]["live_client_as_built"]["max_tokens"] == 400

    # 6 scenarios x 3 runs; the default script pins invalid JSON, a hang, an out-of-vocabulary
    # action and a fenced answer to the pedagogical node.
    assert p["decisions"] == p["llm_calls"] == 18
    assert p["llm_outcomes"] == {"response": 17, "cancelled": 1}
    assert p["fallback"]["by_reason"] == {"parse_error": 2, "timeout": 1}
    assert p["valid_json"]["count"] == 16 and p["valid_json"]["denominator"] == 17
    assert p["valid_json_strict"]["count"] == 15
    assert p["in_vocabulary"]["count"] == 15
    assert set(p["consistency_checks"].values()) == {0}
    assert p["ladder_adherence"]["final"]["rate"] == 1.0
    assert p["latency"]["node"]["n"] == 18 and p["latency"]["node"]["p95_ms"] is not None

    # ...and a leak, an over-length text, a hang and an empty reply to the content adapter.
    assert a["fallback"]["by_reason"] == {"parse_error": 1, "timeout": 1}
    assert f"{confused[0]}#0" in a["answer_leakage"]["leaks_by_scenario_run"]
    generated = a["word_count"]["generated"]
    assert generated["max"] > ev.WORD_LIMIT
    assert generated["compliant"]["count"] == a["generated_texts"] - 1
    assert a["identical_text_repeat"]["pairs"]["denominator"] > 0

    lines = raw.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 18 and results["raw_output"]["written"] is True
    assert not ev.find_secrets(raw.read_text(encoding="utf-8"))


@pytest.mark.parametrize("vllm_key", [None, "not-needed"])
def test_live_mode_refuses_without_an_api_key(tmp_path, monkeypatch, capsys, vllm_key):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    if vllm_key is None:
        monkeypatch.delenv("VLLM_API_KEY", raising=False)
    else:
        monkeypatch.setenv("VLLM_API_KEY", vllm_key)

    def _no_client():
        raise AssertionError("no client may be built without a key")

    monkeypatch.setattr(llm_mod, "get_chat_client", _no_client)
    scenario_file, out = tmp_path / "scenarios.json", tmp_path / "results.json"

    rc = ev.main(["--live", "--scenarios", str(scenario_file), "--out", str(out)])

    assert rc == 2
    assert not out.exists() and not scenario_file.exists()
    assert "REFUSING --live" in capsys.readouterr().err


def test_secret_scan():
    assert ev.find_secrets('{"x": "sk-abcdefghijklmnopqrstuvwx"}')
    assert ev.find_secrets("token=abc", known=["abc"])
    assert not ev.find_secrets('{"text": "a hint about keys in a dictionary"}')
