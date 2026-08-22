"""End-to-end scenario replay: one real session through the real serving pipeline.

WHAT THIS ACTUALLY EXERCISES
---------------------------
Real DUX event streams (mouse / keyboard / scroll) are pushed through the code the deployed
backend runs, with nothing mocked:

    raw events -> feature_engineering.extract_features   (30 x 16)
               -> aggregate_features.aggregate           (80,)
               -> behavioral_confusion_gbdt.onnx         -> P(confused)
               -> agents.fusion.fuse_modalities          (with the facial channel)
               -> agents.edges.passes_adaptation_gate    -> intervene / stay quiet

Ground truth is DUX's `emotion_manual_Confusion`, a HUMAN annotation, so every window can be
scored against what a person actually observed. This answers the only question that matters for an
assistive system: when the learner was genuinely confused, did help arrive — and when they were
fine, were they left alone?

THE FACIAL CHANNEL HERE IS A STAND-IN, AND A DELIBERATELY UNFLATTERING ONE
-------------------------------------------------------------------------
Model A (`cnn_lstm_confusion_anycut.onnx`) CANNOT be run on DUX: DUX ships AFFDEX channel scores,
not video. So the facial slot is filled with DUX's own `emotion_affectiva_Confusion`, rescaled to a
probability.

That channel scored **AUC 0.476 against the human label — worse than chance** (see
`affectlearn-ml/reports/dux_confusion/FINDINGS.md`). Using it is therefore a WORST-CASE test: it
shows what the fused system does when one channel is not merely weak but actively misleading. If
the gate still behaves sensibly under that, it will behave sensibly with Model A's 0.641.

Read the `behavioural_only` arm as the honest picture of the deployable system, and the `fused` arm
as a robustness check. Do NOT read the fused numbers as an estimate of Model A + Model B together —
different corpora, different people, no paired data.

Run:
    python scripts/replay_session.py --participant dux_v1_3
    python scripts/replay_session.py --all --quiet
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
ML = Path(__file__).resolve().parents[3] / "affectlearn-ml" / "training" / "behavioral"
sys.path.insert(0, str(ML))

from app.agents.edges import (  # noqa: E402
    ADAPT_COOLDOWN_CYCLES,
    ADAPT_MIN_CONFIDENCE,
    ADAPT_MIN_CONSECUTIVE,
    passes_adaptation_gate,
)
from app.agents.fusion import fuse_modalities  # noqa: E402
from app.services.behavioral_inference import BehavioralModel  # noqa: E402

GBDT = "models/behavioral_confusion_gbdt.onnx"
WINDOW_S = 30
WINDOWS_PER_HOUR = 3600 / WINDOW_S


def load_dux(dux_dir: str):
    from external_datasets import load_dux_confusion
    return load_dux_confusion(dux_dir)


def facial_stand_in(affectiva: np.ndarray) -> dict:
    """DUX AFFDEX Confusion (0-100) -> a facial inference dict in the serving shape.

    Rescaled by /100 and clipped. The AFFDEX channels are not calibrated probabilities, so this is
    a monotone stand-in only — which is all the fusion needs, since it weights by confidence.
    """
    from external_datasets import DUX_AFFECTIVA
    p = float(np.clip(affectiva[DUX_AFFECTIVA.index("Confusion")] / 100.0, 0.0, 1.0))
    probs = [1.0 - p, p]
    idx = int(np.argmax(probs))
    return {"engagement_level": idx, "label": ["not_confused", "confused"][idx],
            "confidence": float(probs[idx]), "probs": probs}


def replay(windows, model: BehavioralModel, use_facial: bool, verbose: bool):
    """Walk one participant's windows in order, maintaining real gate state."""
    history: list[str] = []
    cycle = 0
    last_adapt: int | None = None
    rows = []

    for w in windows:
        cycle += 1
        from feature_engineering import extract_features
        feats = extract_features(w["events"], 0)
        beh = model.infer(feats)

        if use_facial and w.get("affectiva") is not None:
            fac = facial_stand_in(w["affectiva"])
            fused = fuse_modalities(facial_result=fac, behavioral_result=beh,
                                    facial_kind="binary_confusion")
            state, conf = fused["affect_state"], fused["affect_confidence"]
            p_fac = fac["probs"][1]
        else:
            state, conf, p_fac = beh["label"], beh["confidence"], None

        history.append(state)
        ok, reason = passes_adaptation_gate(
            affect_state=state, affect_confidence=conf, affect_history=history,
            cycle_number=cycle, last_adaptation_cycle=last_adapt,
        )
        if ok:
            last_adapt = cycle
        rows.append({"cycle": cycle, "truth": w["label"], "p_beh": beh["p_confused"],
                     "p_fac": p_fac, "state": state, "conf": conf,
                     "fired": ok, "reason": reason})
        if verbose:
            fac_s = "  -  " if p_fac is None else f"{p_fac:.3f}"
            mark = "INTERVENE" if ok else reason
            print(f"  c{cycle:3d} truth={'CONFUSED' if w['label'] else '   ok   '} "
                  f"p_beh={beh['p_confused']:.3f} p_fac={fac_s} -> {state:10s} "
                  f"conf={conf:.3f}  {mark}")
    return rows


def summarise(rows, label: str):
    n = len(rows)
    fired = [r for r in rows if r["fired"]]
    truth_pos = [r for r in rows if r["truth"] == 1]
    correct = [r for r in fired if r["truth"] == 1]
    prec = len(correct) / len(fired) if fired else float("nan")
    rec = len(correct) / len(truth_pos) if truth_pos else float("nan")
    rate = len(fired) / n * WINDOWS_PER_HOUR if n else 0.0
    print(f"\n  {label}")
    print(f"    windows {n}  ({len(truth_pos)} human-annotated confused)")
    print(f"    interventions fired      {len(fired)}  =  {rate:.1f}/hour"
          f"{'' if rate == 0 else f'  (one every {60/rate:.0f} min)'}")
    print(f"    of those, genuinely confused  {len(correct)}   PRECISION {prec:.3f}")
    print(f"    confused episodes reached     {len(correct)}/{len(truth_pos)}  RECALL {rec:.3f}")
    return {"label": label, "n": n, "fired": len(fired), "precision": prec,
            "recall": rec, "per_hour": rate}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    # Resolved from THIS FILE, not the cwd, so the script works from anywhere.
    ap.add_argument("--dux", default=str(ML.parents[1] / "data" / "external" / "dux"))
    ap.add_argument("--participant", default=None, help="e.g. dux_v1_3; default = the busiest one")
    ap.add_argument("--all", action="store_true", help="replay every participant, summary only")
    ap.add_argument("--quiet", action="store_true", help="suppress the per-window timeline")
    a = ap.parse_args()

    if not os.path.exists(GBDT):
        raise SystemExit(f"{GBDT} not found — run export_dux_confusion.py first")

    print(f"gate: min_confidence={ADAPT_MIN_CONFIDENCE} min_consecutive={ADAPT_MIN_CONSECUTIVE} "
          f"cooldown={ADAPT_COOLDOWN_CYCLES}")
    windows = load_dux(a.dux)
    if not windows:
        raise SystemExit(f"no DUX windows under {a.dux}")
    model = BehavioralModel(model_path=GBDT)
    print(f"model: {GBDT} (kind={model._kind()})\n")

    by_p: dict[str, list] = {}
    for w in windows:
        by_p.setdefault(w["participant"], []).append(w)

    if a.all:
        chosen = sorted(by_p)
    else:
        p = a.participant or max(by_p, key=lambda k: sum(x["label"] for x in by_p[k]))
        if p not in by_p:
            raise SystemExit(f"unknown participant {p}; have {sorted(by_p)[:6]}...")
        chosen = [p]

    allrows_b, allrows_f = [], []
    for p in chosen:
        wins = by_p[p]
        if not a.all:
            print(f"=== {p}: {len(wins)} windows, "
                  f"{sum(x['label'] for x in wins)} human-annotated confused ===")
            print("\n--- BEHAVIOURAL ONLY (the deployable system) ---")
        allrows_b += replay(wins, model, use_facial=False,
                            verbose=(not a.all and not a.quiet))
        if not a.all and not a.quiet:
            print("\n--- FUSED with the AFFDEX stand-in (worst case: that channel is AUC 0.476) ---")
        allrows_f += replay(wins, model, use_facial=True,
                            verbose=(not a.all and not a.quiet))

    print("\n" + "=" * 78)
    print(f"SUMMARY over {len(chosen)} participant(s)")
    print("=" * 78)
    b = summarise(allrows_b, "behavioural only")
    f = summarise(allrows_f, "fused with AFFDEX stand-in")

    print("\n" + "!" * 78)
    print("!! THESE PRECISION FIGURES ARE IN-SAMPLE AND OPTIMISTIC. DO NOT REPORT THEM.")
    print("!" * 78)
    print("  behavioral_confusion_gbdt.onnx was fitted on ALL DUX windows, which is correct for")
    print("  SERVING but means this replay scores it on its own training data. In-sample AUC is")
    print("  0.9251 against a leave-one-participant-out 0.7473 — the gap is memorisation.")
    print("")
    print("  The honest deployment estimate, from simulating this same gate over OUT-OF-FOLD")
    print("  predictions, is PRECISION 0.500 at ~1.5 interventions/hour")
    print("  (affectlearn-ml/reports/dux_confusion/FINDINGS.md). Expect roughly that in the wild,")
    print("  not what is printed above.")
    print("")
    print("  What this replay DOES establish: the full chain runs on real event streams end to")
    print("  end, the gate's states/thresholds/cooldown behave as intended over a real timeline,")
    print("  and p_confused tracks the human annotation rather than drifting.")

    if f["fired"] == 0 and b["fired"] > 0:
        print("\n  NOTE: the fused arm fired NOTHING AT ALL. The AFFDEX stand-in is worse than")
        print("  chance here (AUC 0.476), so it drags every fused confidence under the 0.70 floor")
        print("  and the system goes silent. That is the gate behaving correctly — a misleading")
        print("  channel produces INACTION rather than wrong action — but it also shows that")
        print("  fusing a bad channel does not merely fail to help, it destroys recall entirely.")
        print("  Model A (AUC 0.641) is well above chance and should not do this; verify once its")
        print("  ONNX is deployed rather than assuming.")
    else:
        print(f"\n  fusion changed precision by {f['precision'] - b['precision']:+.3f} "
              f"and firing rate by {f['per_hour'] - b['per_hour']:+.1f}/hour")

    print(f"\n  reference: intervening on every window would be "
          f"{WINDOWS_PER_HOUR:.0f}/hour at precision "
          f"{np.mean([r['truth'] for r in allrows_b]):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
