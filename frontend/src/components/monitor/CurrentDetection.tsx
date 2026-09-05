"use client";

/**
 * What the system detected right now, and what it detected it from.
 *
 * This is the top of the Monitor because detection is the thing being evaluated. Everything below
 * — the gate, the strategy, the hint — is downstream of this reading, and none of it is
 * interpretable without knowing which channel produced the state and how confident it was.
 *
 * TWO CHANNELS, DIFFERENT CONSTRUCTS
 *
 * The two are COMPLEMENTARY, not two opinions on one question: the behavioural GBDT detects
 * confusion and pins bored at 0.0, the geometry model detects disengagement and pins confused at
 * 0.0. So "they disagree" is usually the wrong reading — each is authoritative for the one state
 * it can observe, and only a cycle where both name an ACTIONABLE state is a real conflict. The
 * agreement row says which of those two situations obtains rather than diffing the labels.
 *
 * EVERY NUMBER HERE IS RECORDED
 *
 * Behavioural signals come from the `features` array the backend already persists, labelled
 * positionally by FEATURE_NAMES. Facial signals are the face-presence counters. Nothing is
 * inferred, and a field the backend does not carry renders as "not recorded" rather than 0.
 */

import { AFFECT_COLORS, ago } from "./shared";
import { facialDistribution, behavioralDistribution } from "./prob-labels";
import { ProbBars } from "./ProbBars";

/**
 * Per-bin behavioural feature order. Mirrors `FEATURE_NAMES` in
 * `backend/app/services/feature_engineering.py` — the array is positional and carries no labels,
 * so this list IS the schema. `feature_schema_version` on the payload guards a drift: if it is not
 * 2, the labels below may not describe the columns and the panel says so instead of guessing.
 */
export const FEATURE_NAMES = [
  "mouse_entropy", "mouse_velocity_mean", "mouse_velocity_std", "click_count", "hover_dwell_mean",
  "keystroke_count", "typing_rhythm_std", "backspace_pct", "pause_count",
  "scroll_velocity_mean", "scroll_direction_changes", "scroll_back_runs", "scroll_inactivity_pct",
  "idle_time_pct", "blur_time_pct", "tab_switch_count",
] as const;

const FEATURE_SCHEMA_VERSION = 2;

/** The signals worth surfacing by default, grouped the way a reader thinks about them. */
const SIGNAL_GROUPS: { label: string; keys: readonly string[] }[] = [
  { label: "Mouse", keys: ["mouse_entropy", "mouse_velocity_mean", "click_count", "hover_dwell_mean"] },
  { label: "Typing", keys: ["keystroke_count", "typing_rhythm_std", "backspace_pct", "pause_count"] },
  { label: "Scrolling", keys: ["scroll_velocity_mean", "scroll_direction_changes", "scroll_back_runs"] },
  { label: "Inactivity", keys: ["idle_time_pct", "scroll_inactivity_pct", "blur_time_pct", "tab_switch_count"] },
];

const ACTIONABLE = new Set(["bored", "confused", "frustrated"]);

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function pct(v: number | null): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

/** Mean of each feature column across the window's bins. */
function meanByFeature(features: unknown): number[] | null {
  if (!Array.isArray(features) || features.length === 0) return null;
  const rows = features.filter((r): r is number[] => Array.isArray(r));
  if (rows.length === 0 || rows[0].length !== FEATURE_NAMES.length) return null;
  return FEATURE_NAMES.map((_, i) => {
    const col = rows.map((r) => (typeof r[i] === "number" ? r[i] : 0));
    return col.reduce((a, b) => a + b, 0) / col.length;
  });
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="font-mono text-sm text-foreground">{value}</p>
      {hint ? <p className="text-[10px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function NotRecorded({ what }: { what: string }) {
  return <p className="text-[11px] italic text-muted-foreground">{what} — not recorded</p>;
}

export function CurrentDetection({
  facial,
  behavioral,
  fusion,
  channelFloors,
  stale,
  lastCycleAgeMs,
  timeInStateMs,
}: {
  facial: Record<string, unknown> | null;
  behavioral: Record<string, unknown> | null;
  fusion: Record<string, unknown> | null;
  /** Per-channel confidence floors from /monitor/health, keyed by affect_source. */
  channelFloors?: Record<string, number>;
  stale?: boolean;
  lastCycleAgeMs?: number | null;
  /** How long the current state has held, derived from the session history. */
  timeInStateMs?: number | null;
}) {
  // Fusion is the combined reading when both channels paired; otherwise whichever reported.
  const primary = fusion ?? facial ?? behavioral;
  const state = (primary?.affect_state as string) ?? null;
  const confidence = num(primary?.affect_confidence);
  const source = (primary?.affect_source as string) ?? null;
  const floor = source && channelFloors ? channelFloors[source] : undefined;

  const facialState = (facial?.affect_state as string) ?? null;
  const behavState = (behavioral?.affect_state as string) ?? null;
  const bothActionable =
    facialState && behavState && ACTIONABLE.has(facialState) && ACTIONABLE.has(behavState);

  const schemaOk =
    behavioral?.feature_schema_version == null ||
    behavioral.feature_schema_version === FEATURE_SCHEMA_VERSION;
  const means = schemaOk ? meanByFeature(behavioral?.features) : null;
  const counts = (behavioral?.event_counts as Record<string, number> | undefined) ?? undefined;

  if (!primary) {
    return (
      <p className="text-sm text-muted-foreground">
        No detection yet. A cycle is reported roughly every 30 seconds once a learner is in an
        adaptive session.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {stale ? (
        <div className="rounded-md border border-border bg-muted px-3 py-1.5 text-[11px] text-muted-foreground">
          Not live — last cycle {ago(lastCycleAgeMs)}. This is the most recent detection, not the
          learner&apos;s state now.
        </div>
      ) : null}

      {/* ── the headline reading ── */}
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
        <span
          className="rounded-md px-3 py-1 text-lg font-semibold text-white"
          style={{ background: AFFECT_COLORS[state ?? ""] ?? "#64748b" }}
        >
          {state ?? "no state"}
        </span>
        <span className="font-mono text-2xl text-foreground">{pct(confidence)}</span>
        <span className="text-xs text-muted-foreground">
          confidence{floor != null ? ` · gate ${floor.toFixed(2)}` : ""}
          {confidence != null && floor != null ? (
            <span className={confidence >= floor ? "ml-1 text-emerald-600" : "ml-1 text-amber-600"}>
              {confidence >= floor ? "clears its gate" : "below its gate"}
            </span>
          ) : null}
        </span>
        {timeInStateMs != null ? (
          <span className="text-xs text-muted-foreground">
            held for {Math.round(timeInStateMs / 1000)}s
          </span>
        ) : null}
      </div>

      <p className="text-[11px] text-muted-foreground">
        from <span className="font-mono">{source ?? "unknown channel"}</span>
        {fusion ? " · fused reading (both channels paired this cycle)" : null}
      </p>

      {/* ── the two channels, side by side ── */}
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-md border border-border p-3">
          <p className="mb-2 text-[11px] uppercase tracking-wide text-muted-foreground">
            Facial channel
          </p>
          {facial ? (
            <div className="space-y-2">
              <div className="grid grid-cols-3 gap-2">
                <Stat label="state" value={facialState ?? "—"} />
                <Stat label="P(disengaged)" value={num(facial.p_disengaged)?.toFixed(3) ?? "—"} />
                <Stat
                  label="face"
                  value={pct(num(facial.face_ratio))}
                  hint={`${(facial.frames_with_face as number) ?? "?"}/${(facial.frames_captured as number) ?? "?"} frames`}
                />
              </div>
              <ProbBars
                probs={facialDistribution(facial.probs as number[], facial.model_kind as string)?.probs}
                labels={facialDistribution(facial.probs as number[], facial.model_kind as string)?.labels}
              />
              {facial.face_absent ? (
                <p className="text-[11px] text-amber-600 dark:text-amber-400">
                  Too few frames contained a face — affect was suppressed rather than read from an
                  empty frame.
                </p>
              ) : null}
            </div>
          ) : (
            <NotRecorded what="No facial cycle this window" />
          )}
        </div>

        <div className="rounded-md border border-border p-3">
          <p className="mb-2 text-[11px] uppercase tracking-wide text-muted-foreground">
            Behavioural channel
          </p>
          {behavioral ? (
            <div className="space-y-2">
              <div className="grid grid-cols-3 gap-2">
                <Stat label="state" value={behavState ?? (behavioral.empty_cycle ? "idle" : "—")} />
                <Stat label="P(confused)" value={num(behavioral.p_confused)?.toFixed(3) ?? "—"} />
                <Stat label="bins" value={String(behavioral.n_bins ?? "—")} hint="1s each" />
              </div>
              <ProbBars
                probs={behavioralDistribution(behavioral.probs as number[])?.probs}
                labels={behavioralDistribution(behavioral.probs as number[])?.labels}
              />
              {behavioral.idle ? (
                <p className="text-[11px] text-muted-foreground">
                  Idle window — no interaction events. That is itself the signal, not missing data.
                </p>
              ) : null}
            </div>
          ) : (
            <NotRecorded what="No behavioural cycle this window" />
          )}
        </div>
      </div>

      {/* ── do the channels agree? ── */}
      {facialState && behavState ? (
        <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-[11px]">
          {facialState === behavState ? (
            <>
              Both channels reported <b>{facialState}</b>.
            </>
          ) : bothActionable ? (
            <span className="text-amber-700 dark:text-amber-400">
              Conflict — facial says <b>{facialState}</b>, behavioural says <b>{behavState}</b>.
              Both are actionable states, so this is a genuine disagreement.
            </span>
          ) : (
            <>
              Facial <b>{facialState}</b>, behavioural <b>{behavState}</b> — not a disagreement.
              Each channel is authoritative for the one state it can observe and reports its
              negative class otherwise.
            </>
          )}
          {fusion?.weights ? (
            <span className="ml-1 font-mono text-muted-foreground">
              · weights {JSON.stringify(fusion.weights)}
            </span>
          ) : null}
        </div>
      ) : null}

      {/* ── the signals the behavioural reading was computed from ── */}
      <div>
        <p className="mb-2 text-[11px] uppercase tracking-wide text-muted-foreground">
          Contributing behavioural signals
        </p>
        {!behavioral ? (
          <NotRecorded what="No behavioural cycle" />
        ) : !schemaOk ? (
          <p className="text-[11px] text-amber-600">
            Feature schema v{String(behavioral.feature_schema_version)} does not match the labels
            this build knows (v{FEATURE_SCHEMA_VERSION}), so the columns are not labelled.
          </p>
        ) : means ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {SIGNAL_GROUPS.map((g) => (
              <div key={g.label} className="rounded-md border border-border p-2">
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {g.label}
                </p>
                <dl className="space-y-0.5">
                  {g.keys.map((k) => {
                    const i = FEATURE_NAMES.indexOf(k as (typeof FEATURE_NAMES)[number]);
                    if (i < 0) return null;
                    return (
                      <div key={k} className="flex justify-between gap-2 font-mono text-[11px]">
                        <dt className="truncate text-muted-foreground">{k.replace(/_/g, " ")}</dt>
                        <dd className="tabular-nums text-foreground">{means[i].toFixed(3)}</dd>
                      </div>
                    );
                  })}
                </dl>
              </div>
            ))}
          </div>
        ) : (
          <NotRecorded what="Per-bin features" />
        )}
        {counts ? (
          <p className="mt-2 font-mono text-[11px] text-muted-foreground">
            raw counts · mouse {counts.mouse_sample_count ?? "—"} · clicks{" "}
            {counts.mouse_click_count ?? "—"} · keys {counts.keystroke_count ?? "—"} · scrolls{" "}
            {counts.scroll_event_count ?? "—"}
          </p>
        ) : null}
        <p className="mt-1 text-[10px] text-muted-foreground">
          Window means across {String(behavioral?.n_bins ?? "?")} one-second bins. Aggregate
          features only — raw keystrokes and coordinates are never recorded.
        </p>
      </div>
    </div>
  );
}
