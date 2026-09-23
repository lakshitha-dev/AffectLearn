"use client";

/**
 * Trigger panel for the adaptation loop. Renders only when `NEXT_PUBLIC_AFFECT_DEBUG=1`,
 * alongside the two existing debug overlays.
 *
 * WHY: every adaptation type except one is effectively unreachable by using the product. A
 * `show_breakdown` needs genuine confusion, sustained across two cycles on the same channel,
 * above the confidence floor, on a channel authorised to decide, outside the cooldown, out of the
 * withheld arm, and one rung deep in the section. Nobody has ever seen five of the eight actions
 * on screen, and the one live session anybody has looked at delivered `skip_ahead` three times
 * out of three.
 *
 * TWO MODES, AND THE PANEL ALWAYS SAYS WHICH ONE PRODUCED WHAT — a card that never travelled the
 * loop must not be mistaken for one that did:
 *
 *   RENDER   pushes an adaptation straight into the store. The card, its copy, its dismiss
 *            behaviour. No socket, no backend, no decision. Fastest way to check a rendering fix.
 *   LOOP     calls `POST /dev/simulate-cycle`, which runs the compiled graph with a fabricated
 *            affect reading and pushes the result down the real WebSocket. The verdict comes back
 *            and is displayed verbatim, including when the verdict is "nothing was delivered".
 *
 * A gate reason is not a failure. `state_not_actionable` for `frustrated` is the deployment's
 * `ADAPT_STATES` doing its job, and `withheld_random` is the control arm. The response's notes
 * explain each one; they are rendered as-is rather than summarised.
 */

import { useState } from "react";

import { apiFetch } from "@/lib/api-client";
import { cn } from "@/lib/cn";
import { useAdaptationStore } from "@/stores/adaptation-store";
import { ADAPTATION_ACTIONS, type AdaptationAction } from "@/types/ws-messages";

type AffectState = "bored" | "confused" | "frustrated" | "engaged";

/**
 * Which affect state each action is the ladder response to, and how deep.
 *
 * Mirrors `backend/app/agents/fallbacks.py` `_LADDER`. Duplicated deliberately and marked as
 * such: this is a convenience so one button reaches one action, not a second source of truth. If
 * the two disagree, loop mode reports whatever the strategist actually chose and the discrepancy
 * is visible in the result rather than hidden by it.
 */
const LADDER: Record<AdaptationAction, { affect: AffectState; rung: number }> = {
  show_hint: { affect: "confused", rung: 0 },
  show_breakdown: { affect: "confused", rung: 1 },
  show_alternative: { affect: "confused", rung: 2 },
  show_video: { affect: "confused", rung: 3 },
  increase_difficulty: { affect: "bored", rung: 0 },
  skip_ahead: { affect: "bored", rung: 1 },
  show_encouragement: { affect: "frustrated", rung: 0 },
  simplify: { affect: "frustrated", rung: 1 },
  suggest_break: { affect: "frustrated", rung: 2 },
};

/** Placeholder copy for RENDER mode. Says what it is, so a screenshot cannot mislead. */
const SAMPLE_TEXT: Record<AdaptationAction, string> = {
  show_hint: "Sample hint text — placeholder, not model output.",
  show_breakdown: "First, sample step one.\nThen, sample step two.\nFinally, sample step three.",
  show_alternative: "Sample alternative framing — placeholder, not model output.",
  show_encouragement: "Sample encouragement — placeholder, not model output.",
  simplify: "Sample simplified explanation — placeholder, not model output.",
  increase_difficulty: "Sample challenge question — placeholder, not model output.",
  suggest_break: "Sample break suggestion — placeholder, not model output.",
  skip_ahead: "Sample skip suggestion — placeholder, not model output.",
  show_video: "Sample video introduction — placeholder, not model output.",
};

interface SimulateResult {
  mode: string;
  sessionId: string;
  cycleNumber: number;
  gateReason: string | null;
  shouldAdapt: boolean;
  ladderRung: number | null;
  actionType: string | null;
  text: string | null;
  generated: boolean | null;
  fallback: boolean | null;
  delivered: boolean;
  notes: string[];
  gateConfig: Record<string, unknown>;
}

export function AdaptationDevPanel({ sectionId }: { sectionId: string | undefined }) {
  const pushAdaptation = useAdaptationStore((s) => s.pushAdaptation);
  const reset = useAdaptationStore((s) => s.reset);
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<SimulateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(true);

  const renderOnly = (action: AdaptationAction) => {
    // The queue is append-only and last-match-wins, so a stale item from a previous click would
    // keep winning for the action families this one does not belong to.
    reset();
    pushAdaptation({
      id: `dev-${action}-${Date.now()}`,
      action,
      text: SAMPLE_TEXT[action],
      receivedAt: Date.now(),
    });
    setResult(null);
    setError(null);
  };

  const fullLoop = async (action: AdaptationAction) => {
    if (!sectionId) {
      setError("No section on screen yet.");
      return;
    }
    setBusy(action);
    setError(null);
    try {
      const { affect, rung } = LADDER[action];
      // `actionType` is deliberately NOT sent: the point of this mode is to find out what the
      // strategist picks for that state at that rung. It may not be this action, and that is the
      // most useful thing the panel can tell anyone.
      const res = await apiFetch<SimulateResult>("/dev/simulate-cycle", {
        method: "POST",
        body: JSON.stringify({ sectionId, affectState: affect, rung }),
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        className="fixed bottom-4 left-4 z-50 rounded-lg border border-border bg-surface/90 px-3 py-2 text-xs font-mono text-muted-foreground shadow-lg backdrop-blur hover:text-foreground"
      >
        Adaptation harness
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 left-4 z-50 max-h-[70vh] w-[22rem] overflow-y-auto rounded-lg border border-border bg-surface/95 p-3 text-xs font-mono shadow-lg backdrop-blur">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold text-foreground">Adaptation harness</span>
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          className="text-muted-foreground hover:text-foreground"
          aria-label="Collapse adaptation harness"
        >
          ×
        </button>
      </div>

      <p className="mb-2 leading-relaxed text-muted-foreground">
        <span className="text-foreground">Render</span> pushes the card straight into the store —
        no socket, no decision. <span className="text-foreground">Loop</span> runs the real graph
        and reports the gate&apos;s verdict, which may be that nothing is delivered.
      </p>

      <table className="w-full">
        <tbody>
          {ADAPTATION_ACTIONS.map((action) => (
            <tr key={action}>
              <td className="py-0.5 pr-2 text-muted-foreground">{action}</td>
              <td className="py-0.5 pr-1">
                <button
                  type="button"
                  onClick={() => renderOnly(action)}
                  className="rounded border border-border px-2 py-0.5 text-foreground hover:bg-border"
                >
                  render
                </button>
              </td>
              <td className="py-0.5">
                <button
                  type="button"
                  onClick={() => fullLoop(action)}
                  disabled={busy !== null}
                  className={cn(
                    "rounded border border-border px-2 py-0.5 text-foreground hover:bg-border",
                    busy === action && "opacity-50",
                  )}
                >
                  {busy === action ? "…" : "loop"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <button
        type="button"
        onClick={() => {
          reset();
          setResult(null);
          setError(null);
        }}
        className="mt-2 rounded border border-border px-2 py-0.5 text-muted-foreground hover:text-foreground"
      >
        clear queue
      </button>

      {error && <p className="mt-2 text-destructive">{error}</p>}

      {result && (
        <div className="mt-3 border-t border-border pt-2 leading-relaxed">
          <Row label="gate" value={result.gateReason ?? "—"} />
          <Row label="action" value={result.actionType ?? "none"} />
          <Row label="rung" value={String(result.ladderRung ?? "—")} />
          <Row
            label="source"
            value={
              result.generated === null
                ? "—"
                : result.generated
                  ? "language model"
                  : "rule fallback"
            }
          />
          <Row label="on screen" value={result.delivered ? "yes" : "no"} />
          {result.text && (
            <p className="mt-1 whitespace-pre-wrap text-foreground">{result.text}</p>
          )}
          {result.notes.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-4 text-muted-foreground">
              {result.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-foreground">{value}</span>
    </div>
  );
}
