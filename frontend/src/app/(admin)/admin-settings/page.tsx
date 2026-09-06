"use client";

/**
 * Admin settings — the real configuration, editable.
 *
 * This page previously rendered seven hardcoded `<input disabled>` values ("0.65", "2", "0.80"…)
 * under a banner claiming settings were "read-only during an active pilot study session". None of
 * it was true: the numbers were decorative, they already disagreed with the live gate — which
 * `/monitor/health` reports accurately — and there was no lock, no read-only state, and nothing to
 * be read-only about. It was the last mock page in the admin area.
 *
 * WHY EDITING THESE IS GUARDED
 *
 * These thresholds decide when a learner is interrupted, which makes them the study's independent
 * variables. If one changes halfway through data collection, the cycles before and after are not
 * comparable — and without a trace of the change, an analysis would pool them and report a result
 * that looks fine. Two guards, both surfaced here:
 *
 *   * every change bumps a config VERSION that is stamped onto every research event, so a
 *     mid-study change is visible in the dataset rather than silent;
 *   * a LOCK makes changes refuse outright once collection begins, and unlocking is deliberate.
 *
 * WHY THE PAGE INSISTS ON SAYING WHEN A CHANGE TAKES EFFECT
 *
 * Gate settings apply from the next detection cycle. Study phase and group are resolved once per
 * WebSocket handshake, so they only reach a learner on their next reconnect. An admin who flips
 * phase mid-session and reads the next few cycles as though it had applied would draw a false
 * conclusion, so the page states the difference rather than leaving it to be discovered.
 */

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiRequestError } from "@/lib/api-client";
import { cn } from "@/lib/cn";
import { useStudyGroups, useStudyPhase } from "@/hooks/use-study";
import {
  SYSTEM_CONFIG_KEY,
  patchSystemConfig,
  rotateLlmKey,
  setConfigLock,
  useSystemConfig,
  type ConfigValues,
  type SystemConfig,
} from "@/hooks/use-system-config";

const AFFECT_STATES = ["bored", "confused", "engaged", "frustrated"] as const;
const SOURCES = [
  "behavioral_model",
  "fusion",
  "facial_geometry",
  "category_model",
  "engagement_adapter",
  "performance",
] as const;
const MODES = ["auto", "facial_only", "behavioral_only", "multimodal"] as const;

/** One editable field, with an honest "default vs overridden" marker. */
function Field({
  id,
  label,
  hint,
  overridden,
  disabled,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  overridden?: boolean;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("space-y-1.5", disabled && "opacity-60")}>
      <div className="flex items-baseline gap-2">
        <Label htmlFor={id}>{label}</Label>
        {/* A value and its provenance are different facts. "0.70, the default" and "0.70,
            deliberately chosen" read identically from the number alone, and only one of them is
            a decision worth reporting in a write-up. */}
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
          {overridden ? "overridden" : "default"}
        </span>
      </div>
      {children}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-border bg-surface p-6">
      <h2 className="font-semibold text-foreground">{title}</h2>
      <p className="mb-5 mt-0.5 text-sm text-muted-foreground">{description}</p>
      <div className="grid gap-5 sm:grid-cols-2">{children}</div>
    </section>
  );
}

export default function AdminSettingsPage() {
  const queryClient = useQueryClient();
  const configQ = useSystemConfig();
  const phaseQ = useStudyPhase();
  const groupsQ = useStudyGroups();

  const config = configQ.data;
  const locked = config?.locked ?? false;
  const overridden = new Set(config?.overridden ?? []);

  const [draft, setDraft] = useState<ConfigValues | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset the draft whenever the server's view changes, so a save (or another admin's change)
  // is reflected rather than being overwritten by a stale local copy.
  useEffect(() => {
    if (config) setDraft(config.values);
  }, [config]);

  if (configQ.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading configuration…</p>;
  }
  if (configQ.isError || !config || !draft) {
    return (
      <p className="text-sm text-muted-foreground">
        Configuration could not be read. The settings API may be unavailable.
      </p>
    );
  }

  const set = <K extends keyof ConfigValues>(key: K, value: ConfigValues[K]) =>
    setDraft((d) => (d ? { ...d, [key]: value } : d));

  const dirty = JSON.stringify(draft) !== JSON.stringify(config.values);

  async function save() {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const changed: Partial<Record<keyof ConfigValues, unknown>> = {};
      (Object.keys(draft) as (keyof ConfigValues)[]).forEach((k) => {
        if (JSON.stringify(draft[k]) !== JSON.stringify(config!.values[k])) {
          changed[k] = draft[k];
        }
      });
      const next = await patchSystemConfig(changed);
      queryClient.setQueryData<SystemConfig>([SYSTEM_CONFIG_KEY], next);
      toast.success(`Saved — configuration is now version ${next.version}.`);
    } catch (err) {
      if (err instanceof ApiRequestError && err.errorCode === "CONFIG_LOCKED") {
        setError(
          "Configuration is locked for data collection. Unlock it below to make changes.",
        );
      } else {
        setError(err instanceof Error ? err.message : "Couldn't save. Please try again.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Admin Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Live system configuration. Version{" "}
          <span className="font-mono text-foreground">{config.version}</span> — stamped onto every
          research event, so a change made during collection is visible in the data.
        </p>
      </div>

      {locked ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-800/40 dark:bg-amber-900/20">
          <p className="text-sm text-amber-800 dark:text-amber-300">
            <strong>Locked for data collection.</strong> Thresholds cannot be changed. This is what
            stops a mid-study edit from quietly making cycles before and after incomparable.
          </p>
        </div>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800/40 dark:bg-red-900/20 dark:text-red-400"
        >
          {error}
        </div>
      ) : null}

      <Section
        title="Randomised trial"
        description="What starts and stops data collection. Withheld cycles are the matched control the delivered ones are compared against."
      >
        <Field
          id="withholdRate"
          label="Withhold rate"
          overridden={overridden.has("withholdRate")}
          disabled={locked}
          hint={
            draft.withholdRate === 0
              ? "0 — every eligible moment is delivered. No control arm is being collected."
              : `${Math.round(draft.withholdRate * 100)}% of qualifying moments receive nothing.`
          }
        >
          <Input
            id="withholdRate"
            type="number"
            step="0.05"
            min="0"
            max="1"
            disabled={locked}
            value={draft.withholdRate}
            onChange={(e) => set("withholdRate", Number(e.target.value))}
          />
        </Field>

        <Field
          id="maxPerSession"
          label="Max interventions per session"
          overridden={overridden.has("maxPerSession")}
          disabled={locked}
          hint="Counted across both arms, so they end together."
        >
          <Input
            id="maxPerSession"
            type="number"
            min="0"
            disabled={locked}
            value={draft.maxPerSession}
            onChange={(e) => set("maxPerSession", Number(e.target.value))}
          />
        </Field>
      </Section>

      <Section
        title="Gate thresholds"
        description="When an intervention fires. Applies from the next detection cycle (~30s)."
      >
        <Field
          id="minConfidenceBehavioral"
          label="Confidence floor — behavioural"
          overridden={overridden.has("minConfidenceBehavioral")}
          disabled={locked}
          hint="Detects confusion. Measured precision at 0.50 is 0.500 — a coin flip."
        >
          <Input
            id="minConfidenceBehavioral"
            type="number"
            step="0.05"
            min="0"
            max="1"
            disabled={locked}
            value={draft.minConfidenceBehavioral}
            onChange={(e) => set("minConfidenceBehavioral", Number(e.target.value))}
          />
        </Field>

        <Field
          id="minConfidenceGeometry"
          label="Confidence floor — facial geometry"
          overridden={overridden.has("minConfidenceGeometry")}
          disabled={locked}
          hint="Detects disengagement. Precision 0.872 at 0.70."
        >
          <Input
            id="minConfidenceGeometry"
            type="number"
            step="0.05"
            min="0"
            max="1"
            disabled={locked}
            value={draft.minConfidenceGeometry}
            onChange={(e) => set("minConfidenceGeometry", Number(e.target.value))}
          />
        </Field>

        <Field
          id="minConsecutive"
          label="Consecutive cycles required"
          overridden={overridden.has("minConsecutive")}
          disabled={locked}
          hint={`${draft.minConsecutive} × 30s ≈ ${draft.minConsecutive * 30}s of persistence.`}
        >
          <Input
            id="minConsecutive"
            type="number"
            min="1"
            disabled={locked}
            value={draft.minConsecutive}
            onChange={(e) => set("minConsecutive", Number(e.target.value))}
          />
        </Field>

        <Field
          id="cooldownCycles"
          label="Cooldown cycles"
          overridden={overridden.has("cooldownCycles")}
          disabled={locked}
          hint={`${draft.cooldownCycles} × 30s ≈ ${draft.cooldownCycles * 30}s between interventions.`}
        >
          <Input
            id="cooldownCycles"
            type="number"
            min="0"
            disabled={locked}
            value={draft.cooldownCycles}
            onChange={(e) => set("cooldownCycles", Number(e.target.value))}
          />
        </Field>

        <div className="sm:col-span-2">
          <Field
            id="adaptStates"
            label="Actionable states"
            overridden={overridden.has("adaptStates")}
            disabled={locked}
            hint="States that may trigger an intervention. `engaged` is deliberately excluded — the design leaves engagement undisturbed."
          >
            <div className="flex flex-wrap gap-3">
              {AFFECT_STATES.map((s) => (
                <label key={s} className="flex items-center gap-1.5 text-sm text-foreground">
                  <input
                    type="checkbox"
                    disabled={locked}
                    checked={draft.adaptStates.includes(s)}
                    onChange={(e) =>
                      set(
                        "adaptStates",
                        e.target.checked
                          ? [...draft.adaptStates, s]
                          : draft.adaptStates.filter((x) => x !== s),
                      )
                    }
                    className="h-4 w-4 rounded border-border"
                  />
                  {s}
                </label>
              ))}
            </div>
          </Field>
        </div>
      </Section>

      <Section
        title="Detection channels"
        description="Which channels may act, and whether the fused reading decides."
      >
        <div className="sm:col-span-2">
          <Field
            id="decisiveSources"
            label="Decisive channels"
            overridden={overridden.has("decisiveSources")}
            disabled={locked}
            hint="A channel not listed here is logged but may never intervene alone. Selecting none fails OPEN — every channel becomes decisive."
          >
            <div className="flex flex-wrap gap-3">
              {SOURCES.map((s) => (
                <label key={s} className="flex items-center gap-1.5 text-sm text-foreground">
                  <input
                    type="checkbox"
                    disabled={locked}
                    checked={draft.decisiveSources.includes(s)}
                    onChange={(e) =>
                      set(
                        "decisiveSources",
                        e.target.checked
                          ? [...draft.decisiveSources, s]
                          : draft.decisiveSources.filter((x) => x !== s),
                      )
                    }
                    className="h-4 w-4 rounded border-border"
                  />
                  <span className="font-mono text-xs">{s}</span>
                </label>
              ))}
            </div>
          </Field>
        </div>

        <Field
          id="fusionDrivesDecision"
          label="Fusion drives the decision"
          overridden={overridden.has("fusionDrivesDecision")}
          disabled={locked}
          hint="Off is correct here: the two channels detect disjoint states, so averaging them halves both below the gate floor."
        >
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input
              id="fusionDrivesDecision"
              type="checkbox"
              disabled={locked}
              checked={draft.fusionDrivesDecision}
              onChange={(e) => set("fusionDrivesDecision", e.target.checked)}
              className="h-4 w-4 rounded border-border"
            />
            {draft.fusionDrivesDecision ? "On" : "Off"}
          </label>
        </Field>

        <Field
          id="forcedMode"
          label="Detection mode"
          overridden={overridden.has("forcedMode")}
          disabled={locked}
          hint="`auto` pairs both modalities when available."
        >
          <select
            id="forcedMode"
            disabled={locked}
            value={draft.forcedMode}
            onChange={(e) => set("forcedMode", e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm"
          >
            {MODES.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </Field>
      </Section>

      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={!dirty || saving || locked}>
          {saving ? "Saving…" : "Save changes"}
        </Button>
        {dirty && !locked ? (
          <button
            type="button"
            onClick={() => setDraft(config.values)}
            className="text-sm text-muted-foreground underline-offset-2 hover:underline"
          >
            Discard
          </button>
        ) : null}
        <span className="text-xs text-muted-foreground">
          Gate settings apply from the next detection cycle.
        </span>
      </div>

      <StudySection
        phase={phaseQ.data?.phase}
        transitionedAt={phaseQ.data?.transitionedAt ?? null}
        assigned={groupsQ.data?.items?.length ?? null}
      />

      <LlmKeySection config={config} onRotated={() => configQ.refetch()} />

      <LockSection locked={locked} onToggled={() => configQ.refetch()} />
    </div>
  );
}

function StudySection({
  phase,
  transitionedAt,
  assigned,
}: {
  phase?: string;
  transitionedAt: string | null;
  assigned: number | null;
}) {
  return (
    <section className="rounded-lg border border-border bg-surface p-6">
      <h2 className="font-semibold text-foreground">Study</h2>
      <p className="mt-0.5 text-sm text-muted-foreground">
        Phase is global; group is per account. Only <span className="font-mono">phase_b</span> +{" "}
        <span className="font-mono">adaptive</span> is eligible for an intervention.
      </p>
      <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs uppercase tracking-wide text-muted-foreground">Phase</dt>
          <dd className="font-mono text-foreground">{phase ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-muted-foreground">Assigned learners</dt>
          <dd className="font-mono text-foreground">{assigned ?? "—"}</dd>
        </div>
      </dl>
      {/* Stated because getting this wrong produces a confident misreading: an admin who flips
          phase and watches the next few cycles would conclude it had no effect. */}
      <p className="mt-4 text-xs text-muted-foreground">
        Phase and group are resolved once per WebSocket handshake, so a change reaches a learner on
        their <strong>next reconnect</strong> — not mid-session. Change them from{" "}
        <a href="/ab-groups" className="underline underline-offset-2">
          A/B Groups
        </a>
        {transitionedAt ? ` · last changed ${new Date(transitionedAt).toLocaleString()}` : null}
      </p>
    </section>
  );
}

function LlmKeySection({
  config,
  onRotated,
}: {
  config: SystemConfig;
  onRotated: () => void;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { llmKey } = config;

  async function rotate() {
    setBusy(true);
    setErr(null);
    try {
      await rotateLlmKey(value.trim());
      setValue("");
      toast.success("Key replaced — it takes effect immediately.");
      onRotated();
    } catch (e) {
      if (e instanceof ApiRequestError && e.errorCode === "ENCRYPTION_UNAVAILABLE") {
        setErr("No encryption secret is configured, so a key cannot be stored safely.");
      } else {
        setErr(e instanceof Error ? e.message : "Couldn't save the key.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-lg border border-border bg-surface p-6">
      <h2 className="font-semibold text-foreground">LLM API key</h2>
      <p className="mt-0.5 text-sm text-muted-foreground">
        Used to generate hints and challenge questions. Stored encrypted and{" "}
        <strong className="text-foreground">never displayed</strong> — only the last four
        characters, which is enough to confirm which key is installed and not enough to use it.
      </p>

      <p className="mt-4 text-sm text-muted-foreground">
        {llmKey.configured ? (
          <>
            Installed: <span className="font-mono text-foreground">sk-…{llmKey.hint}</span>
            {llmKey.updatedAt
              ? ` · changed ${new Date(llmKey.updatedAt).toLocaleString()}`
              : null}
          </>
        ) : (
          "No key stored here — the deployment is using whatever its environment supplies."
        )}
      </p>

      {llmKey.canRotate ? (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Input
            type="password"
            autoComplete="off"
            placeholder="Paste a new key"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="max-w-sm"
          />
          <Button onClick={rotate} disabled={busy || value.trim().length < 8}>
            {busy ? "Saving…" : "Replace key"}
          </Button>
        </div>
      ) : (
        <p className="mt-4 text-sm text-amber-700 dark:text-amber-400">
          Rotation is unavailable: no encryption secret is configured, and storing a key in the
          clear is not an option.
        </p>
      )}

      {err ? (
        <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">
          {err}
        </p>
      ) : null}
    </section>
  );
}

/**
 * The lock, presented as a danger zone in both directions.
 *
 * Unlocking is the risky action, not locking: it is the one that lets a threshold move underneath
 * a running study. So the unlock path requires the two-stage confirmation, following
 * `AccountDataControls`.
 */
function LockSection({ locked, onToggled }: { locked: boolean; onToggled: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  async function toggle(next: boolean) {
    setBusy(true);
    try {
      await setConfigLock(next);
      toast.success(next ? "Settings locked." : "Settings unlocked.");
      setConfirming(false);
      onToggled();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't change the lock.");
    } finally {
      setBusy(false);
    }
  }

  if (!locked) {
    return (
      <section className="rounded-lg border border-border bg-surface p-6">
        <h2 className="font-semibold text-foreground">Lock for data collection</h2>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Locking makes thresholds read-only. Do this before the first participant, so a later edit
          cannot silently split your dataset into incomparable halves.
        </p>
        <Button className="mt-4" variant="outline" onClick={() => toggle(true)} disabled={busy}>
          {busy ? "Locking…" : "Lock settings"}
        </Button>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-red-200 bg-red-50 p-6 dark:border-red-800/40 dark:bg-red-900/10">
      <h2 className="font-semibold text-foreground">Unlock settings</h2>
      <p className="mt-0.5 text-sm text-muted-foreground">
        Settings are locked. Unlocking during collection is recorded, and the configuration version
        will change — cycles recorded before and after are not comparable and must be analysed as
        separate groups.
      </p>
      {!confirming ? (
        <Button
          className="mt-4 border-red-300 text-red-700 dark:text-red-400"
          variant="outline"
          onClick={() => setConfirming(true)}
        >
          Unlock…
        </Button>
      ) : (
        <div className="mt-4 flex items-center gap-3">
          <Button variant="destructive" onClick={() => toggle(false)} disabled={busy}>
            {busy ? "Unlocking…" : "Yes, unlock"}
          </Button>
          <button
            type="button"
            onClick={() => setConfirming(false)}
            className="text-sm text-muted-foreground underline-offset-2 hover:underline"
          >
            Cancel
          </button>
        </div>
      )}
    </section>
  );
}
