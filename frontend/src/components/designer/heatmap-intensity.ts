/**
 * Affect-heatmap column definitions + intensity/color mapping (Story 7.3).
 *
 * Pure, framework-free helpers shared by every cell so the four columns stay
 * visually consistent and the band logic lives in ONE place.
 *
 * TAILWIND PURGE GOTCHA (IMPORTANT): Tailwind only emits classes it can find as
 * complete static strings. We therefore return FULL literal class names from a
 * lookup map (e.g. the string bg-affect-confused/35), never interpolated strings
 * like bg-affect-[state]/[opacity] (those get purged and render with no
 * background). The same class set is also added to the tailwind.config.ts
 * safelist as belt-and-suspenders.
 *
 * INTENSITY BAND → OPACITY MAPPING (cell BACKGROUND, AC2):
 *   0–20%   → /15   light tint   (barely visible)
 *   20–40%  → /35   medium tint
 *   40–60%  → /65   strong tint
 *   60–100% → /100  bold / fully saturated (demands attention)
 * Boundary convention: a band's LOWER bound is exclusive of the band below and
 * the cutoff value belongs to the HIGHER band, i.e. `pct >= 60` is "bold",
 * `pct >= 40` is "strong", `pct >= 20` is "medium", else "light". `pct` is
 * clamped to 0 so negatives never escape the light band.
 *
 * TEXT LEGIBILITY (AC2/AC7): on the saturated 60%+ band the affect color is dark
 * enough that white text is required for contrast; the lighter bands use the
 * normal foreground. The percentage NUMBER is always rendered, so legibility
 * never depends on the tint alone (color is never the sole signal).
 */
import type { AffectState, HeatmapSectionRow } from "@/types/analytics";

export interface AffectColumn {
  state: AffectState;
  label: string;
  /** Which `*Pct` field on a {@link HeatmapSectionRow} this column reads. */
  pctKey: keyof HeatmapSectionRow;
}

/**
 * Column order is fixed by the UX spec (AC1): Engaged, Confused, Bored,
 * Frustrated. Each maps to its `*Pct` field and affect color token.
 */
export const AFFECT_COLUMNS: readonly AffectColumn[] = [
  { state: "engaged", label: "Engaged", pctKey: "engagedPct" },
  { state: "confused", label: "Confused", pctKey: "confusedPct" },
  { state: "bored", label: "Bored", pctKey: "boredPct" },
  { state: "frustrated", label: "Frustrated", pctKey: "frustratedPct" },
] as const;

type Band = "light" | "medium" | "strong" | "bold";

/** Resolve the intensity band for a percentage (see boundary convention above). */
export function intensityBand(pct: number): Band {
  const value = Number.isFinite(pct) ? Math.max(0, pct) : 0;
  if (value >= 60) return "bold";
  if (value >= 40) return "strong";
  if (value >= 20) return "medium";
  return "light";
}

/**
 * Full static background-class lookup keyed by state then band. Every string is
 * a complete literal (e.g. bg-affect-engaged/35) so Tailwind keeps it on purge.
 */
const BG_CLASS: Record<AffectState, Record<Band, string>> = {
  engaged: {
    light: "bg-affect-engaged/15",
    medium: "bg-affect-engaged/35",
    strong: "bg-affect-engaged/65",
    bold: "bg-affect-engaged/100",
  },
  confused: {
    light: "bg-affect-confused/15",
    medium: "bg-affect-confused/35",
    strong: "bg-affect-confused/65",
    bold: "bg-affect-confused/100",
  },
  bored: {
    light: "bg-affect-bored/15",
    medium: "bg-affect-bored/35",
    strong: "bg-affect-bored/65",
    bold: "bg-affect-bored/100",
  },
  frustrated: {
    light: "bg-affect-frustrated/15",
    medium: "bg-affect-frustrated/35",
    strong: "bg-affect-frustrated/65",
    bold: "bg-affect-frustrated/100",
  },
};

/**
 * The cell background class for an affect state at a given percentage band.
 * Pure: same input → same literal class string.
 */
export function intensityClass(state: AffectState, pct: number): string {
  return BG_CLASS[state][intensityBand(pct)];
}

/**
 * Text-color class keeping the percentage legible on its cell background:
 * white on the saturated bold band, normal foreground otherwise.
 */
export function intensityTextClass(pct: number): string {
  return intensityBand(pct) === "bold" ? "text-white" : "text-foreground";
}
