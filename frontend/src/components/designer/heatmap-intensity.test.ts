/**
 * Tests for the affect-heatmap intensity helper (Story 7.3, AC2).
 *
 * Verifies the band→class mapping for every affect state and the documented
 * boundary convention (cutoff value belongs to the higher band: >=60 bold,
 * >=40 strong, >=20 medium, else light), plus the text-legibility treatment.
 */

import { describe, expect, it } from "vitest";

import type { AffectState } from "@/types/analytics";
import {
  AFFECT_COLUMNS,
  intensityBand,
  intensityClass,
  intensityTextClass,
} from "./heatmap-intensity";

const STATES: AffectState[] = ["engaged", "confused", "bored", "frustrated"];

describe("AFFECT_COLUMNS", () => {
  it("defines the four columns in the UX-spec order with the right pct keys", () => {
    expect(AFFECT_COLUMNS.map((c) => c.state)).toEqual([
      "engaged",
      "confused",
      "bored",
      "frustrated",
    ]);
    expect(AFFECT_COLUMNS.map((c) => c.label)).toEqual([
      "Engaged",
      "Confused",
      "Bored",
      "Frustrated",
    ]);
    expect(AFFECT_COLUMNS.map((c) => c.pctKey)).toEqual([
      "engagedPct",
      "confusedPct",
      "boredPct",
      "frustratedPct",
    ]);
  });
});

describe("intensityBand", () => {
  it("maps representative values into the documented bands", () => {
    expect(intensityBand(0)).toBe("light");
    expect(intensityBand(10)).toBe("light");
    expect(intensityBand(25)).toBe("medium");
    expect(intensityBand(50)).toBe("strong");
    expect(intensityBand(75)).toBe("bold");
    expect(intensityBand(100)).toBe("bold");
  });

  it("treats each cutoff value as belonging to the higher band", () => {
    expect(intensityBand(20)).toBe("medium");
    expect(intensityBand(40)).toBe("strong");
    expect(intensityBand(60)).toBe("bold");
  });

  it("clamps negatives and non-finite values into the light band", () => {
    expect(intensityBand(-5)).toBe("light");
    expect(intensityBand(Number.NaN)).toBe("light");
  });
});

describe("intensityClass", () => {
  it("returns full static affect-color classes per band for every state", () => {
    for (const state of STATES) {
      expect(intensityClass(state, 5)).toBe(`bg-affect-${state}/15`);
      expect(intensityClass(state, 25)).toBe(`bg-affect-${state}/35`);
      expect(intensityClass(state, 50)).toBe(`bg-affect-${state}/65`);
      expect(intensityClass(state, 80)).toBe(`bg-affect-${state}/100`);
    }
  });

  it("applies the boundary convention per state", () => {
    expect(intensityClass("confused", 60)).toBe("bg-affect-confused/100");
    expect(intensityClass("confused", 40)).toBe("bg-affect-confused/65");
    expect(intensityClass("confused", 20)).toBe("bg-affect-confused/35");
  });
});

describe("intensityTextClass", () => {
  it("uses white text only on the saturated bold band", () => {
    expect(intensityTextClass(75)).toBe("text-white");
    expect(intensityTextClass(60)).toBe("text-white");
    expect(intensityTextClass(59)).toBe("text-foreground");
    expect(intensityTextClass(0)).toBe("text-foreground");
  });
});
