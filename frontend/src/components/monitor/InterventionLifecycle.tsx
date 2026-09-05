"use client";

/**
 * Every intervention in the session, from the detection that triggered it to what happened next.
 *
 * This is the view that answers "why did the learner see that hint", which previously required
 * reading backend logs. Each stage is a recorded event; nothing here is inferred.
 *
 * THE OUTCOME IS DELIBERATELY NOT CALLED AN OUTCOME
 *
 * Nothing in the record links an intervention to a later state. Self-reports are triggered by
 * section completion, not by delivery, and carry no reference to a hint. So the last column is the
 * next detected state IN TIME, presented as sequence. Calling it an effect would assert causation
 * the data cannot support, and a research dashboard that quietly does that is worse than one that
 * shows less.
 *
 * SILENCE IS NOT A FINDING
 *
 * Only skip_ahead, increase_difficulty and hint dismissal report an interaction at all. A hint with
 * no recorded response was not necessarily ignored — nothing was listening for most of its
 * lifetime. That is stated rather than rendered as an empty "no response" cell.
 */

import { useState } from "react";

import type { SessionIntervention } from "@/types/monitor";
import { AFFECT_COLORS } from "./shared";

const GAP_EXPLANATION: Record<string, string> = {
  hint_text:
    "The text shown to the learner is not on this row — it was recorded from a later build onward.",
  strategy_reason:
    "The strategist's rationale is not on this row — it was recorded from a later build onward.",
  delivery_unconfirmed:
    "Generated but no delivery event. A failed send now emits one, so on newer rows this means the send is genuinely unaccounted for.",
  no_response_recorded:
    "No interaction recorded. Not evidence the learner ignored it — only some action types report at all.",
};

function clock(ms: number | null | undefined): string {
  if (ms == null) return "—";
  return new Date(ms).toLocaleTimeString(undefined, { hour12: false });
}

function Pill({ state }: { state: string | null | undefined }) {
  if (!state) return <span className="text-muted-foreground">—</span>;
  return (
    <span
      className="rounded px-1.5 py-0.5 text-[11px] font-medium text-white"
      style={{ background: AFFECT_COLORS[state] ?? "#64748b" }}
    >
      {state}
    </span>
  );
}

function Stage({
  label,
  when,
  children,
}: {
  label: string;
  when?: number | null;
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-[7rem_1fr] gap-2 py-1.5">
      <div>
        <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="font-mono text-[10px] tabular-nums text-muted-foreground">{clock(when)}</p>
      </div>
      <div className="min-w-0 text-xs text-foreground">{children}</div>
    </div>
  );
}

function NotRecorded({ reason }: { reason: string }) {
  return <p className="text-[11px] italic text-muted-foreground">{reason}</p>;
}

function Row({ item }: { item: SessionIntervention }) {
  const [open, setOpen] = useState(false);

  const strat = (item.strategy ?? {}) as Record<string, unknown>;
  const trig = (item.triggered ?? {}) as Record<string, unknown>;
  const del = (item.delivered ?? {}) as Record<string, unknown>;
  const failed = (item.deliveryFailed ?? null) as Record<string, unknown> | null;
  const resp = (item.response ?? null) as Record<string, unknown> | null;
  const next = item.nextState;
  const gaps = new Set(item.missing ?? []);

  return (
    <div className="border-t border-border">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-left hover:bg-muted/40"
      >
        <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
          #{item.cycle_number}
        </span>
        <Pill state={item.detection.state} />
        <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
          {item.detection.confidence != null
            ? `${Math.round(item.detection.confidence * 100)}%`
            : "—"}
        </span>
        <span className="text-muted-foreground">→</span>
        <span className="text-xs font-medium text-foreground">
          {(strat.action_type as string) ?? (trig.variant as string) ?? "no action"}
        </span>
        {failed ? (
          <span className="rounded bg-red-100 px-1 text-[10px] text-red-700 dark:bg-red-900/40 dark:text-red-300">
            delivery failed
          </span>
        ) : del.action ? (
          <span className="rounded bg-emerald-100 px-1 text-[10px] text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
            delivered
          </span>
        ) : (
          <span className="rounded bg-amber-100 px-1 text-[10px] text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
            not delivered
          </span>
        )}
        {resp ? (
          <span className="font-mono text-[10px] text-muted-foreground">
            · {String(resp.interaction)}
          </span>
        ) : null}
        <span className="ml-auto text-[10px] text-muted-foreground">{open ? "hide" : "detail"}</span>
      </button>

      {open ? (
        <div className="divide-y divide-border border-t border-border bg-muted/20 px-3 py-1">
          <Stage label="Trigger" when={item.gate?.timestamp}>
            <Pill state={item.detection.state} />{" "}
            {item.detection.confidence != null
              ? `at ${Math.round(item.detection.confidence * 100)}%`
              : ""}{" "}
            <span className="text-muted-foreground">
              from {item.detection.source ?? "unknown channel"}
            </span>
          </Stage>

          <Stage label="Gate" when={item.gate?.timestamp}>
            {item.gate?.reason ? (
              <>
                <span className="font-mono">{item.gate.reason}</span>
                {item.gate.affect_source ? (
                  <span className="text-muted-foreground"> · ruled on {item.gate.affect_source}</span>
                ) : null}
              </>
            ) : (
              <NotRecorded reason="No gate verdict on this cycle." />
            )}
          </Stage>

          <Stage label="Decision" when={strat.timestamp as number}>
            {item.strategy ? (
              <>
                <span className="font-medium">{String(strat.action_type)}</span>
                <span className="text-muted-foreground">
                  {" "}
                  · urgency {String(strat.urgency)} ·{" "}
                  {strat.fallback
                    ? `rule-based (${String(strat.fallback_reason ?? "fallback")})`
                    : "LLM"}
                </span>
                {strat.reason ? (
                  <p className="mt-1 rounded bg-background px-2 py-1 text-[11px] italic text-foreground">
                    &ldquo;{String(strat.reason)}&rdquo;
                  </p>
                ) : gaps.has("strategy_reason") ? (
                  <NotRecorded reason={GAP_EXPLANATION.strategy_reason} />
                ) : null}
              </>
            ) : (
              <NotRecorded reason="The gate withheld, so no strategy ran." />
            )}
          </Stage>

          <Stage label="Hint" when={trig.timestamp as number}>
            {trig.text ? (
              <>
                <p className="whitespace-pre-wrap rounded bg-background px-2 py-1.5 text-[11px] text-foreground">
                  {String(trig.text)}
                </p>
                {trig.text_truncated ? (
                  <p className="mt-0.5 text-[10px] text-amber-600">
                    Stored text was capped — the learner may have seen more.
                  </p>
                ) : null}
              </>
            ) : gaps.has("hint_text") ? (
              <NotRecorded reason={GAP_EXPLANATION.hint_text} />
            ) : item.triggered ? (
              <NotRecorded reason="This action carries no text (a selective action such as skip_ahead)." />
            ) : (
              <NotRecorded reason="No content was generated." />
            )}
            {item.triggered ? (
              <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                {String(trig.variant)} ·{" "}
                {trig.generated
                  ? "LLM-generated"
                  : trig.fallback
                    ? `pre-written (${String(trig.fallback_reason ?? "fallback")})`
                    : "selective action"}
              </p>
            ) : null}
          </Stage>

          <Stage label="Delivery" when={(del.timestamp as number) ?? (failed?.timestamp as number)}>
            {failed ? (
              <span className="text-red-700 dark:text-red-400">
                Send failed — {String(failed.reason ?? "reason not recorded")}. The learner was
                offered help and did not receive it.
              </span>
            ) : del.action ? (
              <>
                Sent as <span className="font-mono">{String(del.action)}</span>
                {del.adaptation_id ? (
                  <span className="text-muted-foreground">
                    {" "}
                    · id {String(del.adaptation_id).slice(0, 8)}
                  </span>
                ) : null}
              </>
            ) : gaps.has("delivery_unconfirmed") ? (
              <NotRecorded reason={GAP_EXPLANATION.delivery_unconfirmed} />
            ) : (
              <NotRecorded reason="Nothing to deliver." />
            )}
          </Stage>

          <Stage label="Response" when={resp?.timestamp as number}>
            {resp ? (
              <>
                Learner <span className="font-medium">{String(resp.interaction)}</span> it
              </>
            ) : (
              <NotRecorded reason={GAP_EXPLANATION.no_response_recorded} />
            )}
          </Stage>

          <Stage label="Next state" when={next?.at}>
            {next ? (
              <>
                <Pill state={next.state} />{" "}
                <span className="text-muted-foreground">
                  at cycle #{next.cycle_number}
                  {next.confidence != null ? `, ${Math.round(next.confidence * 100)}%` : ""}
                </span>
                <p className="mt-0.5 text-[10px] italic text-muted-foreground">
                  The next reading in time. Nothing in the record links a hint to a later state, so
                  this is sequence, not effect.
                </p>
              </>
            ) : (
              <NotRecorded reason="No further detection in this session." />
            )}
          </Stage>
        </div>
      ) : null}
    </div>
  );
}

export function InterventionLifecycle({
  interventions,
  loading,
}: {
  interventions: SessionIntervention[];
  loading?: boolean;
}) {
  if (loading) return <p className="text-sm text-muted-foreground">Loading session history…</p>;

  if (interventions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No interventions in this session. That is a normal outcome: the gate withholds unless a
        state is actionable, confident enough, sustained across cycles, out of cooldown, and from a
        channel authorised to act.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-border">
      {interventions.map((it) => (
        <Row key={`${it.cycle_number}`} item={it} />
      ))}
    </div>
  );
}
