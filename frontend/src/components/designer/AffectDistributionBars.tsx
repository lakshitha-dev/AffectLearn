"use client";

import { cn } from "@/lib/cn";
import type { AffectDistribution } from "@/types/analytics";
import { AFFECT_COLUMNS } from "./heatmap-intensity";
import { AFFECT_BAR_FILL } from "./section-hotspot";

/**
 * Panel 1 — Affect Distribution horizontal bars (Story 7.4, AC2).
 *
 * One bar per affect state in the FIXED order Engaged, Confused, Bored,
 * Frustrated (reusing `AFFECT_COLUMNS` so order/labels/`*Pct` keys match the 7.3
 * heatmap). Each bar: a track + a filled portion (`bg-affect-{state}`, width =
 * `min(pct, 100)%`), the affect label, and the `Math.round(pct)%` text ALWAYS
 * visible so color is never the sole signal (a11y).
 *
 * Percentages are PER-LEARNER and MAY sum to >100 (a learner can show multiple
 * states) — these are independent bars, NOT a normalized stacked 100% bar.
 *
 * `compact` renders a denser variant (no panel chrome) for reuse inside the
 * hotspot tooltip (AC5).
 */
interface AffectDistributionBarsProps {
  distribution: AffectDistribution;
  compact?: boolean;
}

export function AffectDistributionBars({
  distribution,
  compact = false,
}: AffectDistributionBarsProps) {
  return (
    <div className={cn("space-y-3", compact && "space-y-2")}>
      {AFFECT_COLUMNS.map((column) => {
        const raw = distribution[column.pctKey as keyof AffectDistribution];
        const pct = Number.isFinite(raw) ? Math.max(0, raw) : 0;
        const rounded = Math.round(pct);
        const width = Math.min(pct, 100);
        return (
          <div
            key={column.state}
            className="flex items-center gap-3"
            aria-label={`${column.label} ${rounded}%`}
          >
            <span
              className={cn(
                "shrink-0 text-muted-foreground",
                compact ? "w-16 text-xs" : "w-20 text-sm",
              )}
            >
              {column.label}
            </span>
            <div
              className={cn(
                "relative flex-1 overflow-hidden rounded-full bg-border/60",
                compact ? "h-2" : "h-3",
              )}
            >
              <div
                className={cn("h-full rounded-full", AFFECT_BAR_FILL[column.state])}
                style={{ width: `${width}%` }}
              />
            </div>
            <span
              className={cn(
                "shrink-0 text-right font-semibold tabular-nums text-foreground",
                compact ? "w-9 text-xs" : "w-11 text-sm",
              )}
            >
              {rounded}%
            </span>
          </div>
        );
      })}
    </div>
  );
}
