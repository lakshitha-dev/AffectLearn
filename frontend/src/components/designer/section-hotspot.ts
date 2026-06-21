/**
 * Section-detail affect-bar colors + content-hotspot helpers (Story 7.4).
 *
 * Pure, framework-free helpers shared by the affect-distribution bars and the
 * content-hotspot preview so color tokens and threshold logic live in ONE place.
 *
 * TAILWIND PURGE GOTCHA (same as `heatmap-intensity.ts`): Tailwind only emits
 * classes it can find as complete static strings, so we return FULL literal class
 * names from lookup maps (e.g. `bg-affect-confused`), never interpolated strings
 * like `bg-affect-${state}`. These class names are ALSO added to the
 * tailwind.config.ts safelist as belt-and-suspenders.
 */
import type { AffectState, ParagraphAnnotation } from "@/types/analytics";

/**
 * Paragraph-hotspot thresholds (AC4 / Open Question 2). Mirrors the 7.1
 * `CONFUSION_HOTSPOT_THRESHOLD = 30`: a block is a hotspot when its (section-level)
 * confused OR frustrated share reaches 30%. Single source → trivial to tune.
 */
export const HOTSPOT_CONFUSED_THRESHOLD = 30;
export const HOTSPOT_FRUSTRATED_THRESHOLD = 30;

/** Solid fill class per affect state (full opacity) for the distribution bars. */
export const AFFECT_BAR_FILL: Record<AffectState, string> = {
  engaged: "bg-affect-engaged",
  confused: "bg-affect-confused",
  bored: "bg-affect-bored",
  frustrated: "bg-affect-frustrated",
};

/** Text-color class per affect state (used for the hotspot annotation chip). */
export const AFFECT_TEXT: Record<AffectState, string> = {
  engaged: "text-affect-engaged",
  confused: "text-affect-confused",
  bored: "text-affect-bored",
  frustrated: "text-affect-frustrated",
};

/**
 * A block is a HOTSPOT when its affect distribution is non-null AND a problematic
 * share (confused or frustrated) crosses the threshold. Null distribution → never
 * a hotspot. Boundary: 29 → false, 30 → true.
 */
export function isHotspot(annotation: ParagraphAnnotation): boolean {
  const d = annotation.affectDistribution;
  if (!d) return false;
  return (
    d.confusedPct >= HOTSPOT_CONFUSED_THRESHOLD ||
    d.frustratedPct >= HOTSPOT_FRUSTRATED_THRESHOLD
  );
}

/**
 * The inline annotation string for a hotspot, e.g. "68% confusion here" or
 * "45% frustration here". The DOMINANT problematic share wins; confusion wins ties.
 * Returns null when the annotation is not a hotspot.
 */
export function hotspotLabel(annotation: ParagraphAnnotation): string | null {
  const d = annotation.affectDistribution;
  if (!isHotspot(annotation) || !d) return null;
  if (d.frustratedPct > d.confusedPct) {
    return `${Math.round(d.frustratedPct)}% frustration here`;
  }
  return `${Math.round(d.confusedPct)}% confusion here`;
}
