"use client";

import { useState } from "react";

import { cn } from "@/lib/cn";
import { ContentBlockRenderer } from "@/components/learning/ContentBlockRenderer";
import type { ContentBlock } from "@/types/course";
import type { ParagraphAnnotation, TemporalBin } from "@/types/analytics";
import { AffectDistributionBars } from "./AffectDistributionBars";
import { hotspotLabel, isHotspot } from "./section-hotspot";

/**
 * Panel 3 — Content Preview with hotspot highlighting (Story 7.4, AC4–AC7).
 *
 * Renders the section's content blocks read-only, in order, reusing
 * `ContentBlockRenderer`. Each `ParagraphAnnotation` is mapped onto a
 * `ContentBlock`-shaped object:
 *   { id: blockId, blockType, content: { text: text ?? "" }, sortOrder: paragraphIndex }
 *
 * MAPPING CAVEAT: the detail endpoint returns only the extracted `text` per
 * annotation, NOT the full original `content` object. This maps cleanly for
 * `text`/`callout` blocks (both read `content.text`). For `code`/`image`/
 * `quiz`/`exercise` blocks the renderer expects richer `content` it does not
 * carry — `ContentBlockRenderer` try/catches and degrades to "Content
 * unavailable" rather than crashing. The hotspot preview is therefore primarily
 * meaningful for text/callout content (where paragraph-level affect commentary
 * lands); a richer non-text render would require fetching full course content
 * (future enhancement — out of scope).
 *
 * HOTSPOT (AC4): a block whose section-level `affectDistribution` crosses the
 * confused/frustrated threshold gets an amber tint + amber left border + an
 * inline "% confusion here" chip. Hovering/focusing it reveals the four-affect
 * breakdown (AC5). Clicking it expands the SECTION-LEVEL temporal distribution
 * (AC6) — the SAME chart for every hotspot, since the 7.1 contract has no
 * per-paragraph temporal data (labeled honestly).
 *
 * NO-ISSUES (AC7): when no block is a hotspot (or `insufficientData`), content
 * renders normally with the exact copy "No significant affect issues detected".
 */
interface ContentHotspotPreviewProps {
  content: ParagraphAnnotation[];
  temporalDistribution: TemporalBin[];
  insufficientData: boolean;
}

function toContentBlock(annotation: ParagraphAnnotation): ContentBlock {
  return {
    id: annotation.blockId,
    blockType: annotation.blockType as ContentBlock["blockType"],
    content: { text: annotation.text ?? "" },
    sortOrder: annotation.paragraphIndex,
    // Fields the read-only renderer does not use; filled to satisfy the type.
    variantKey: "",
    variantGroup: "",
    sectionId: "",
    createdAt: "",
    updatedAt: "",
  };
}

/** Section-level temporal distribution (AC6) — same for every hotspot. */
function TemporalDistribution({ bins }: { bins: TemporalBin[] }) {
  const hasData = bins.length > 0 && bins.some((b) => b.confusedPct > 0);

  return (
    <div className="mt-3 rounded-md border border-border bg-background/40 p-3">
      <p className="text-xs font-semibold text-foreground">
        Where confusion peaks in this section
      </p>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        Section-level (best-effort) — the same distribution applies to every
        hotspot; per-paragraph timing is not yet logged.
      </p>
      {hasData ? (
        <div className="mt-3 flex items-end gap-1.5" aria-hidden="true">
          {bins.map((bin) => (
            <div key={bin.binIndex} className="flex flex-1 flex-col items-center gap-1">
              <div className="flex h-16 w-full items-end rounded-sm bg-border/40">
                <div
                  className="w-full rounded-sm bg-affect-confused"
                  style={{ height: `${Math.min(Math.max(bin.confusedPct, 0), 100)}%` }}
                />
              </div>
              <span className="text-[10px] tabular-nums text-muted-foreground">
                {Math.round(bin.confusedPct)}%
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-xs text-muted-foreground">
          No temporal data available
        </p>
      )}
    </div>
  );
}

function HotspotBlock({
  annotation,
  temporalDistribution,
}: {
  annotation: ParagraphAnnotation;
  temporalDistribution: TemporalBin[];
}) {
  const [expanded, setExpanded] = useState(false);
  const [hovered, setHovered] = useState(false);
  const label = hotspotLabel(annotation);
  const distribution = annotation.affectDistribution!;
  const breakdownId = `hotspot-breakdown-${annotation.blockId}`;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onFocus={() => setHovered(true)}
        onBlur={() => setHovered(false)}
        aria-expanded={expanded}
        aria-describedby={breakdownId}
        aria-label={`Affect hotspot: ${label}. Activate to view where confusion peaks in this section.`}
        className="block w-full rounded-r-md border-l-4 border-affect-confused bg-affect-confused/10 py-2 pl-4 pr-2 text-left transition-colors hover:bg-affect-confused/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-affect-confused"
      >
        <span className="mb-2 inline-flex items-center rounded-full bg-affect-confused/20 px-2 py-0.5 text-xs font-semibold text-affect-confused">
          {label}
        </span>
        <div className="text-foreground">
          <ContentBlockRenderer block={toContentBlock(annotation)} previewMode />
        </div>
      </button>

      {/* Hover/focus breakdown popover (AC5) — accessible, always queryable. */}
      <div
        id={breakdownId}
        role="tooltip"
        aria-label="Affect breakdown for this hotspot"
        className={cn(
          "mt-2 rounded-md border border-border bg-surface p-3 shadow-sm transition-opacity",
          hovered ? "opacity-100" : "pointer-events-none absolute -left-[9999px] opacity-0",
        )}
      >
        <p className="mb-2 text-xs font-semibold text-foreground">
          Affect breakdown
        </p>
        <AffectDistributionBars distribution={distribution} compact />
      </div>

      {expanded ? (
        <TemporalDistribution bins={temporalDistribution} />
      ) : null}
    </div>
  );
}

export function ContentHotspotPreview({
  content,
  temporalDistribution,
  insufficientData,
}: ContentHotspotPreviewProps) {
  const anyHotspot =
    !insufficientData && content.some((annotation) => isHotspot(annotation));

  return (
    <div className="space-y-4">
      {!anyHotspot ? (
        <p className="rounded-md border border-border bg-background/40 px-4 py-3 text-sm text-muted-foreground">
          No significant affect issues detected
        </p>
      ) : null}

      <div className="space-y-4">
        {content.map((annotation) => {
          const hotspot = !insufficientData && isHotspot(annotation);
          if (hotspot) {
            return (
              <HotspotBlock
                key={annotation.blockId}
                annotation={annotation}
                temporalDistribution={temporalDistribution}
              />
            );
          }
          return (
            <div key={annotation.blockId}>
              <ContentBlockRenderer block={toContentBlock(annotation)} previewMode />
            </div>
          );
        })}
      </div>
    </div>
  );
}
