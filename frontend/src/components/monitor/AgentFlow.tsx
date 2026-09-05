"use client";

/**
 * One cycle's journey from signal to intervention, as an ordered chain of recorded facts.
 *
 * The old view was a node graph showing which graph nodes ran. That answers "did the pipeline
 * execute" but not "what did it decide and why", which is the question a research demo needs.
 *
 * EVERY STEP IS ANCHORED TO AN EVENT
 *
 *   collected  <- the counters on behavioral_affect_detected / facial_affect_detected
 *   detected   <- affect_state + affect_confidence on those events
 *   gated      <- adaptation_gate on learner_profile_updated
 *   decided    <- strategy_decided (action_type, urgency, fallback_reason)
 *   generated  <- adaptation_triggered (variant, generated vs fallback)
 *   delivered  <- adaptation_delivered
 *   responded  <- adaptation_interaction
 *
 * A step with no event renders "not recorded" and, where the reason is structural, says what the
 * reason is. That distinction matters: "the gate withheld so no strategy ran" and "a strategy ran
 * but the backend does not store its rationale" look identical as a blank box and are completely
 * different facts.
 *
 * WHAT THIS CANNOT SHOW, AND WHY
 *
 * The hint TEXT and the strategist's RATIONALE are built in memory and never written to any event,
 * so they are irrecoverable for LLM-generated content. Delivery FAILURE emits nothing at all — a
 * generated adaptation with no matching delivery is the only evidence, and it is shown as
 * "unconfirmed" rather than "failed", because those are not the same claim.
 */

import type { SessionCycle } from "@/types/monitor";

type StepStatus = "done" | "withheld" | "missing" | "pending";

interface Step {
  key: string;
  label: string;
  status: StepStatus;
  at: number | null;
  detail: string;
  note?: string;
}

const DOT: Record<StepStatus, string> = {
  done: "bg-emerald-500",
  withheld: "bg-slate-400",
  missing: "bg-amber-500",
  pending: "bg-slate-300",
};

/** Gate reasons that mean "the pipeline stopped here on purpose", not "something is broken". */
const WITHHELD_EXPLANATION: Record<string, string> = {
  ok: "",
  not_eligible: "Phase A or the control group — this learner never receives adaptations by design.",
  no_affect: "No affect state this cycle, so there was nothing to act on.",
  state_not_actionable: "The detected state is not in ADAPT_STATES (engaged is deliberately excluded).",
  low_confidence: "Confidence was below this channel's floor.",
  not_sustained: "The state had not persisted for the required consecutive cycles.",
  cooldown: "An adaptation fired too recently.",
  channel_advisory: "This channel is inferred and logged but not authorised to intervene alone.",
};

function clock(ms: number | null | undefined): string {
  if (ms == null) return "—";
  return new Date(ms).toLocaleTimeString(undefined, { hour12: false });
}

function buildSteps(cycle: SessionCycle | null): Step[] {
  if (!cycle) return [];

  const f = cycle.facial as Record<string, unknown> | null;
  const b = cycle.behavioural as Record<string, unknown> | null;
  const fused = cycle.fused as Record<string, unknown> | null;
  const gate = cycle.gate;
  const strat = cycle.strategy as Record<string, unknown> | null;
  const trig = cycle.triggered as Record<string, unknown> | null;
  const del = cycle.delivered as Record<string, unknown> | null;

  const counts = (b?.event_counts as Record<string, number>) ?? {};
  const collected: string[] = [];
  if (b) {
    collected.push(
      `${counts.mouse_sample_count ?? 0} mouse · ${counts.keystroke_count ?? 0} keys · ${counts.scroll_event_count ?? 0} scrolls${b.idle ? " · idle" : ""}`,
    );
  }
  if (f) {
    collected.push(`${(f.frames_with_face as number) ?? 0}/${(f.frames_captured as number) ?? 0} frames with a face`);
  }

  const primary = fused ?? f ?? b;
  const state = primary?.affect_state as string | undefined;
  const conf = primary?.affect_confidence as number | undefined;

  const gateReason = gate?.reason ?? null;
  const passed = gateReason === "ok";

  const steps: Step[] = [
    {
      key: "collected",
      label: "Signals collected",
      status: collected.length ? "done" : "missing",
      at: cycle.started_at,
      detail: collected.join("  ·  ") || "No cycle payload",
    },
    {
      key: "detected",
      label: "Detection",
      status: state ? "done" : "missing",
      at: (primary?.timestamp as number) ?? cycle.started_at,
      detail: state
        ? `${state} at ${conf != null ? `${Math.round(conf * 100)}%` : "unknown confidence"}${primary?.affect_source ? ` · ${primary.affect_source}` : ""}`
        : "No state resolved this cycle (empty cycle, learner absent, or inference error)",
    },
    {
      key: "gated",
      label: "Gate decision",
      status: gateReason ? (passed ? "done" : "withheld") : "missing",
      at: gate?.timestamp ?? null,
      detail: gateReason
        ? passed
          ? "Passed — this cycle may intervene"
          : `Withheld · ${gateReason}`
        : "No gate verdict recorded for this cycle",
      note: gateReason && !passed ? WITHHELD_EXPLANATION[gateReason] : undefined,
    },
    {
      key: "decided",
      label: "Agent decision",
      status: strat ? "done" : passed ? "missing" : "withheld",
      at: (strat?.timestamp as number) ?? null,
      detail: strat
        ? `${strat.action_type} · urgency ${strat.urgency}${strat.fallback ? ` · rule-based (${strat.fallback_reason ?? "fallback"})` : " · LLM"}`
        : passed
          ? "Gate passed but no strategy event recorded"
          : "Not reached — the gate withheld",
      note: strat
        ? "The strategist's own rationale is parsed and then discarded by the backend, so the reason it gave is not recoverable."
        : undefined,
    },
    {
      key: "generated",
      label: "Hint generated",
      status: trig ? "done" : strat ? "withheld" : "withheld",
      at: (trig?.timestamp as number) ?? null,
      detail: trig
        ? `${trig.variant} · ${trig.generated ? "LLM-generated" : trig.fallback ? `pre-written (${trig.fallback_reason ?? "fallback"})` : "selective action, no text"}`
        : strat
          ? "No content generated (no_action, or a selective action with no text)"
          : "Not reached",
      note: trig?.generated
        ? "The generated text itself is not stored on any event, so what the learner read cannot be shown."
        : undefined,
    },
    {
      key: "delivered",
      label: "Delivered to learner",
      status: del ? "done" : trig ? "missing" : "withheld",
      at: (del?.timestamp as number) ?? null,
      detail: del
        ? `${del.action} sent`
        : trig
          ? "Generated but no delivery recorded"
          : "Not reached",
      note:
        !del && trig
          ? "A failed send emits no event, so this is unconfirmed rather than known to have failed."
          : undefined,
    },
  ];

  return steps;
}

export function AgentFlow({ cycle, cycleLabel }: { cycle: SessionCycle | null; cycleLabel?: string }) {
  const steps = buildSteps(cycle);

  if (steps.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No cycle selected. Pick a row in the detection timeline, or wait for the next cycle.
      </p>
    );
  }

  return (
    <div>
      {cycleLabel ? (
        <p className="mb-3 font-mono text-[11px] text-muted-foreground">{cycleLabel}</p>
      ) : null}
      <ol className="space-y-0">
        {steps.map((s, i) => (
          <li key={s.key} className="flex gap-3">
            {/* rail */}
            <div className="flex flex-col items-center">
              <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${DOT[s.status]}`} />
              {i < steps.length - 1 ? <span className="w-px flex-1 bg-border" /> : null}
            </div>
            <div className="min-w-0 flex-1 pb-4">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-sm font-medium text-foreground">{s.label}</span>
                <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                  {clock(s.at)}
                </span>
                {s.status === "missing" ? (
                  <span className="rounded bg-amber-100 px-1 text-[10px] text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                    not recorded
                  </span>
                ) : null}
              </div>
              <p className="text-xs text-muted-foreground">{s.detail}</p>
              {s.note ? (
                <p className="mt-0.5 text-[10px] italic text-muted-foreground">{s.note}</p>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
