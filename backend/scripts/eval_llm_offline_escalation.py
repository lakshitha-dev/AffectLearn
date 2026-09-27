"""How far the Pedagogical Agent jumps up the confusion ladder in the offline evaluation.

    python scripts/eval_llm_offline_escalation.py

`ladder_adherence` in eval_llm_offline_results.json counts any action at or above the scenario's
rung as adherent, so a jump straight to the last rung (show_video) passes. The system prompt
allows an early video only on strong evidence: three or more wrong answers, or a learner request
after text help (rung >= 1). This reads the per-run raw file of the live run and the fixed
scenario set and reports, for confusion scenarios:

  skipped_ahead          final action above the scenario's rung
  early_video            show_video before the last rung
  early_video_no_basis   early_video without either kind of evidence the prompt names

Aggregates only are written (eval_llm_offline_escalation.json); the raw file stays gitignored.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "eval_llm_offline_raw_live.jsonl"
SCENARIOS = HERE / "eval_llm_offline_scenarios.json"
OUT = HERE / "eval_llm_offline_escalation.json"


def main() -> int:
    rows = [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines() if line]
    scen = {s["scenario_id"]: s for s in json.loads(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]}
    n = skipped = early = no_basis = 0
    by_pattern: Counter = Counter()
    for r in rows:
        s = scen[r["scenario_id"]]
        if s["affect_state"] != "confused":
            continue
        n += 1
        ladder, rung = s["ladder"], int(s["ladder_rung"])
        act = r["pedagogical"]["final_action"]
        idx = ladder.index(act) if act in ladder else None
        if idx is not None and idx > min(rung, len(ladder) - 1):
            skipped += 1
        if act == "show_video" and rung < len(ladder) - 1:
            early += 1
            basis = (s["learner_activity"]["quiz_incorrect_count"] >= 3
                     or (bool(s["learner_request"]) and rung >= 1))
            if not basis:
                no_basis += 1
                by_pattern[(s["activity_pattern"], bool(s["learner_request"]), rung)] += 1
    out = {"_note": __doc__.strip().splitlines()[0], "confused_decisions": n,
           "skipped_ahead": skipped, "early_video": early, "early_video_no_basis": no_basis,
           "early_video_no_basis_by_cell": {f"{p}|request={q}|rung={k}": v
                                            for (p, q, k), v in sorted(by_pattern.items())}}
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
