"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import {
  DIFFERENTIAL_POINTS,
  isComplete,
  isVisible,
  visibleAnswers,
  type InstrumentDef,
  type InstrumentItem,
} from "./instruments";

export interface InstrumentSubmission {
  responses: Record<string, string>;
  skipped: boolean;
  /** When the form was first shown (ISO), so time-to-answer is recoverable. */
  shownAt: string;
}

interface InstrumentFormProps {
  def: InstrumentDef;
  onSubmit: (submission: InstrumentSubmission) => Promise<void> | void;
  isSubmitting?: boolean;
  /** Offer a Skip button; a skip is recorded, with no answers. */
  allowSkip?: boolean;
  submitLabel?: string;
  /** Compact layout for the in-lesson overlay. */
  compact?: boolean;
}

/**
 * Renders one questionnaire from its definition (`instruments.ts`). Submit stays disabled until
 * every shown, required item is answered; follow-up items appear only when their condition holds
 * and are never submitted while hidden.
 */
export function InstrumentForm({
  def,
  onSubmit,
  isSubmitting = false,
  allowSkip = false,
  submitLabel = "Continue",
  compact = false,
}: InstrumentFormProps) {
  const [values, setValues] = useState<Record<string, string>>({});
  const shownAt = useRef(new Date().toISOString());
  const complete = isComplete(def, values);

  const set = (id: string, value: string) => setValues((v) => ({ ...v, [id]: value }));

  return (
    <form
      aria-label={def.title}
      className={cn("space-y-6", compact ? "" : "max-w-2xl mx-auto px-8 py-12")}
      onSubmit={(e) => {
        e.preventDefault();
        if (complete && !isSubmitting) {
          void onSubmit({
            responses: visibleAnswers(def, values), skipped: false, shownAt: shownAt.current,
          });
        }
      }}
    >
      <div>
        <h1 className={cn("font-semibold text-foreground", compact ? "text-lg" : "text-2xl")}>
          {def.title}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">{def.intro}</p>
      </div>

      <div className={cn("rounded-xl border border-border bg-surface space-y-6",
        compact ? "p-4" : "p-6")}>
        {def.items.filter((item) => isVisible(item, values)).map((item) => (
          <ItemField key={item.id} item={item} value={values[item.id] ?? ""}
            onChange={(v) => set(item.id, v)} name={`${def.name}-${item.id}`} />
        ))}
      </div>

      <div className="flex gap-3">
        <Button type="submit" disabled={!complete || isSubmitting}
          aria-disabled={!complete || isSubmitting} data-track={`${def.name}-submit`}>
          {isSubmitting ? "Saving…" : submitLabel}
        </Button>
        {allowSkip && (
          <Button type="button" variant="outline" disabled={isSubmitting}
            data-track={`${def.name}-skip`}
            onClick={() => void onSubmit({ responses: {}, skipped: true, shownAt: shownAt.current })}>
            Skip
          </Button>
        )}
      </div>
    </form>
  );
}

function ItemField({
  item,
  value,
  onChange,
  name,
}: {
  item: InstrumentItem;
  value: string;
  onChange: (v: string) => void;
  name: string;
}) {
  const labelId = `${name}-label`;
  if (item.kind === "differential") {
    return (
      <fieldset className="space-y-2">
        <legend id={labelId} className="sr-only">{`${item.left} to ${item.right}`}</legend>
        <div className="flex items-center gap-3" role="radiogroup" aria-labelledby={labelId}>
          <span className="w-28 text-right text-sm text-foreground">{item.left}</span>
          <div className="flex gap-2">
            {DIFFERENTIAL_POINTS.map((point) => (
              <label key={point} className="flex flex-col items-center cursor-pointer">
                <input
                  type="radio" name={name} value={point} checked={value === point}
                  onChange={() => onChange(point)}
                  aria-label={`${point} of 7, from ${item.left} to ${item.right}`}
                  className="h-4 w-4 accent-primary"
                />
              </label>
            ))}
          </div>
          <span className="w-28 text-sm text-foreground">{item.right}</span>
        </div>
      </fieldset>
    );
  }
  return (
    <fieldset className="space-y-3">
      <legend id={labelId} className="text-sm font-medium text-foreground">{item.prompt}</legend>
      <div role="radiogroup" aria-labelledby={labelId} className="flex flex-wrap gap-2">
        {item.options.map((option) => {
          const checked = value === option.value;
          return (
            <label key={option.value} className={cn(
              "flex items-center gap-2 rounded-lg border px-3 py-2 cursor-pointer transition-colors",
              checked ? "border-primary bg-primary/5" : "border-border hover:bg-accent",
            )}>
              <input type="radio" name={name} value={option.value} checked={checked}
                onChange={() => onChange(option.value)} className="h-4 w-4 accent-primary" />
              <span className="text-sm text-foreground">{option.label}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
