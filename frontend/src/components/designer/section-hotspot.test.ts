/**
 * Tests for the section-detail hotspot helpers (Story 7.4, AC4 / Task 2.2).
 *
 * Covers the threshold boundaries (29 → false, 30 → true), null distribution →
 * not a hotspot, and the dominant-share label (confusion vs frustration).
 */

import { describe, it, expect } from "vitest";

import type { ParagraphAnnotation } from "@/types/analytics";
import { hotspotLabel, isHotspot } from "./section-hotspot";

function annotation(
  affect: Partial<{
    engagedPct: number;
    confusedPct: number;
    boredPct: number;
    frustratedPct: number;
  }> | null,
): ParagraphAnnotation {
  return {
    blockId: "b1",
    paragraphIndex: 0,
    blockType: "text",
    text: "hello",
    affectDistribution: affect
      ? {
          engagedPct: 0,
          confusedPct: 0,
          boredPct: 0,
          frustratedPct: 0,
          ...affect,
        }
      : null,
  };
}

describe("isHotspot", () => {
  it("is false when affectDistribution is null", () => {
    expect(isHotspot(annotation(null))).toBe(false);
  });

  it("is false at 29% confusion (below threshold)", () => {
    expect(isHotspot(annotation({ confusedPct: 29 }))).toBe(false);
  });

  it("is true at exactly 30% confusion (boundary belongs to hotspot)", () => {
    expect(isHotspot(annotation({ confusedPct: 30 }))).toBe(true);
  });

  it("is true when frustration crosses the threshold", () => {
    expect(isHotspot(annotation({ frustratedPct: 45 }))).toBe(true);
  });

  it("is false when neither confused nor frustrated crosses", () => {
    expect(
      isHotspot(annotation({ engagedPct: 90, boredPct: 80 })),
    ).toBe(false);
  });
});

describe("hotspotLabel", () => {
  it("returns null for a non-hotspot", () => {
    expect(hotspotLabel(annotation({ confusedPct: 10 }))).toBeNull();
  });

  it("reports confusion when confused dominates", () => {
    expect(hotspotLabel(annotation({ confusedPct: 68, frustratedPct: 12 }))).toBe(
      "68% confusion here",
    );
  });

  it("reports frustration when frustration dominates", () => {
    expect(hotspotLabel(annotation({ confusedPct: 20, frustratedPct: 45 }))).toBe(
      "45% frustration here",
    );
  });
});
