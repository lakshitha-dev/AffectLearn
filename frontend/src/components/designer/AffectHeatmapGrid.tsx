"use client";

import { useRef } from "react";
import { useRouter } from "next/navigation";

import { cn } from "@/lib/cn";
import type { HeatmapSectionRow } from "@/types/analytics";
import {
  AFFECT_COLUMNS,
  intensityClass,
  intensityTextClass,
} from "./heatmap-intensity";

/**
 * Affect Heatmap Grid (Story 7.3) — the designer "aha moment" component.
 *
 * Section titles as ROWS (rendered top-to-bottom as received — the backend
 * already orders by course position, so we do NOT re-sort), four affect-state
 * COLUMNS (Engaged / Confused / Bored / Frustrated). Each cell is color-coded by
 * its column's `--affect-*` token, with background INTENSITY scaling by the
 * percentage band via the single `intensityClass` helper (one place → all four
 * columns consistent). Percentages can sum to >100 per row (per-learner basis).
 *
 * INTERACTION (AC3/AC4): the whole row hover-highlights with a pointer cursor
 * and is clickable → navigates to `/analytics/{courseId}/sections/{sectionId}`
 * (the Story 7.4 detail route). Cell colour is never the sole signal — the
 * numeric percentage is always shown (AC7).
 *
 * KEYBOARD-NAV MODEL (AC7): a roving-tabindex over the section rows. Exactly one
 * row is tabbable at a time; ArrowUp/ArrowDown (and ArrowLeft/ArrowRight, treated
 * as up/down since the navigable unit is the whole clickable row) move focus
 * between rows; Enter / Space activates the focused row → section detail. A
 * visible focus ring is applied. Cell-level horizontal traversal is intentionally
 * collapsed to row-level because the row (not an individual cell) is the
 * navigation target in 7.3 (cell-level drill-down is Story 7.4's concern).
 */

interface AffectHeatmapGridProps {
  courseId: string;
  sections: HeatmapSectionRow[];
}

const GRID_TEMPLATE = "minmax(10rem,2fr) repeat(4, minmax(4.5rem, 1fr))";

export function AffectHeatmapGrid({
  courseId,
  sections,
}: AffectHeatmapGridProps) {
  const router = useRouter();
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);
  // Roving tabindex: the index of the currently-tabbable row.
  const focusedIndex = useRef(0);

  const hrefFor = (sectionId: string) =>
    `/analytics/${courseId}/sections/${sectionId}`;

  const openSection = (sectionId: string) => {
    router.push(hrefFor(sectionId));
  };

  const moveFocus = (from: number, delta: number) => {
    const next = Math.min(Math.max(from + delta, 0), sections.length - 1);
    if (next === from) return;
    focusedIndex.current = next;
    rowRefs.current[next]?.focus();
  };

  const handleRowKeyDown = (
    event: React.KeyboardEvent<HTMLDivElement>,
    index: number,
    sectionId: string,
  ) => {
    switch (event.key) {
      case "ArrowDown":
      case "ArrowRight":
        event.preventDefault();
        moveFocus(index, 1);
        break;
      case "ArrowUp":
      case "ArrowLeft":
        event.preventDefault();
        moveFocus(index, -1);
        break;
      case "Home":
        event.preventDefault();
        moveFocus(index, -index);
        break;
      case "End":
        event.preventDefault();
        moveFocus(index, sections.length - 1 - index);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        openSection(sectionId);
        break;
      default:
        break;
    }
  };

  return (
    <div
      role="grid"
      aria-label="Affect distribution by section"
      aria-rowcount={sections.length + 1}
      className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm"
    >
      {/* Header row */}
      <div
        role="row"
        className="grid items-center border-b border-border bg-background/40"
        style={{ gridTemplateColumns: GRID_TEMPLATE }}
      >
        <div
          role="columnheader"
          className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
        >
          Section
        </div>
        {AFFECT_COLUMNS.map((column) => (
          <div
            key={column.state}
            role="columnheader"
            className="px-3 py-3 text-center text-xs font-semibold uppercase tracking-wide text-muted-foreground"
          >
            {column.label}
          </div>
        ))}
      </div>

      {/* Section rows */}
      {sections.map((section, index) => {
        const limited =
          section.insufficientData || section.confidence === "low";

        return (
          <div
            key={section.sectionId}
            ref={(el) => {
              rowRefs.current[index] = el;
            }}
            role="row"
            aria-rowindex={index + 2}
            tabIndex={index === focusedIndex.current ? 0 : -1}
            onClick={() => openSection(section.sectionId)}
            onFocus={() => {
              focusedIndex.current = index;
            }}
            onKeyDown={(event) =>
              handleRowKeyDown(event, index, section.sectionId)
            }
            className={cn(
              "grid cursor-pointer items-stretch border-b border-border transition-colors last:border-b-0",
              "hover:bg-primary-soft/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
              limited && "opacity-80",
            )}
            style={{ gridTemplateColumns: GRID_TEMPLATE }}
          >
            {/* Section title (row header) */}
            <div
              role="rowheader"
              className="flex items-center gap-2 px-4 py-3 text-left text-sm font-medium text-foreground"
            >
              <span className="truncate">{section.sectionTitle}</span>
              {limited ? (
                <span className="inline-flex shrink-0 items-center rounded-full bg-muted/15 px-2 py-0.5 text-xs font-medium text-muted-foreground">
                  Limited data
                </span>
              ) : null}
            </div>

            {/* Affect cells */}
            {AFFECT_COLUMNS.map((column) => {
              const pct = section[column.pctKey] as number;
              const rounded = Math.round(pct);
              return (
                <div
                  key={column.state}
                  role="gridcell"
                  aria-label={`${section.sectionTitle} — ${column.label} ${rounded}%`}
                  className={cn(
                    "flex items-center justify-center px-3 py-3 text-sm font-semibold tabular-nums",
                    intensityClass(column.state, pct),
                    intensityTextClass(pct),
                  )}
                >
                  {rounded}%
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
