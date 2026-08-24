/**
 * The two modalities use DIFFERENT class orders, and mixing them up mislabels every bar.
 *
 *   behavioural  ("engaged", "bored", "confused", "frustrated")
 *   facial       ("bored", "confused", "engaged", "frustrated")
 *
 * The monitor previously labelled both with the facial order, so a behavioural probs[0] —
 * which is `engaged` — was drawn as `bored`. These tests pin each order to its modality.
 */

import { describe, it, expect } from "vitest";
import { behavioralDistribution, facialDistribution } from "./prob-labels";

describe("behavioralDistribution", () => {
  it("labels using the BEHAVIOURAL order, not the facial one", () => {
    // probs[0] is `engaged` under BEHAVIORAL_CLASS_ORDER.
    const d = behavioralDistribution([0.7, 0.0, 0.3, 0.0])!;
    const engaged = d.labels.indexOf("engaged");
    const confused = d.labels.indexOf("confused");
    expect(d.probs[engaged]).toBe(0.7);
    expect(d.probs[confused]).toBe(0.3);
  });

  it("drops the states the deployed models cannot emit", () => {
    const d = behavioralDistribution([0.6, 0.0, 0.4, 0.0])!;
    expect(d.labels).not.toContain("bored");
    expect(d.labels).not.toContain("frustrated");
    expect(d.labels.sort()).toEqual(["confused", "engaged"]);
  });

  it("treats a 2-slot payload as a binary confusion head", () => {
    const d = behavioralDistribution([0.25, 0.75])!;
    expect(d.labels).toEqual(["not confused", "confused"]);
    expect(d.probs).toEqual([0.25, 0.75]);
  });

  it("returns null for empty or missing input", () => {
    expect(behavioralDistribution(null)).toBeNull();
    expect(behavioralDistribution([])).toBeNull();
  });
});

describe("facialDistribution", () => {
  it("labels using the FACIAL order", () => {
    // probs[1] is `confused` under AFFECT_CLASS_ORDER.
    const d = facialDistribution([0.1, 0.6, 0.3, 0.0])!;
    expect(d.probs[d.labels.indexOf("confused")]).toBe(0.6);
    expect(d.probs[d.labels.indexOf("engaged")]).toBe(0.3);
  });

  it("handles the deployed 2-class head", () => {
    const d = facialDistribution([0.52, 0.48])!;
    expect(d.labels).toEqual(["not confused", "confused"]);
  });

  it("never returns more labels than probs", () => {
    const d = facialDistribution([0.5, 0.5])!;
    expect(d.labels).toHaveLength(d.probs.length);
  });
});
