/**
 * Tests for the Content Hotspot Preview (Story 7.4, AC4–AC7).
 *
 * Covers: a hotspot annotation renders the amber highlight + inline
 * "% confusion here" annotation while a non-hotspot does not; hover/focus reveals
 * the breakdown; click expands then collapses the temporal distribution (and
 * shows "No temporal data available" for empty bins); the no-issues state shows
 * the exact "No significant affect issues detected" copy.
 */

import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";

import type { ParagraphAnnotation, TemporalBin } from "@/types/analytics";
import { ContentHotspotPreview } from "./ContentHotspotPreview";

const hotspot: ParagraphAnnotation = {
  blockId: "b-hot",
  paragraphIndex: 0,
  blockType: "text",
  text: "Subnet masks are confusing.",
  affectDistribution: {
    engagedPct: 30,
    confusedPct: 68,
    boredPct: 10,
    frustratedPct: 12,
  },
};

const calm: ParagraphAnnotation = {
  blockId: "b-calm",
  paragraphIndex: 1,
  blockType: "text",
  text: "This part is clear.",
  affectDistribution: {
    engagedPct: 90,
    confusedPct: 5,
    boredPct: 2,
    frustratedPct: 1,
  },
};

const temporal: TemporalBin[] = [
  { binIndex: 0, confusedPct: 20 },
  { binIndex: 1, confusedPct: 70 },
];

describe("ContentHotspotPreview", () => {
  it("highlights a hotspot block with amber treatment + inline annotation", () => {
    render(
      <ContentHotspotPreview
        content={[hotspot, calm]}
        temporalDistribution={temporal}
        insufficientData={false}
      />,
    );

    const trigger = screen.getByRole("button", { name: /Affect hotspot/ });
    expect(trigger.className).toContain("bg-affect-confused/10");
    expect(trigger.className).toContain("border-affect-confused");
    expect(within(trigger).getByText("68% confusion here")).toBeInTheDocument();
  });

  it("does not highlight a non-hotspot block", () => {
    render(
      <ContentHotspotPreview
        content={[hotspot, calm]}
        temporalDistribution={temporal}
        insufficientData={false}
      />,
    );
    // Only the hotspot is a button; the calm block renders as plain text.
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByText("This part is clear.")).toBeInTheDocument();
  });

  it("reveals the affect breakdown on hover", () => {
    render(
      <ContentHotspotPreview
        content={[hotspot]}
        temporalDistribution={temporal}
        insufficientData={false}
      />,
    );
    const trigger = screen.getByRole("button", { name: /Affect hotspot/ });
    const breakdown = screen.getByRole("tooltip", {
      name: "Affect breakdown for this hotspot",
    });
    expect(breakdown.className).toContain("opacity-0");
    fireEvent.mouseEnter(trigger);
    expect(breakdown.className).toContain("opacity-100");
  });

  it("expands and collapses the temporal distribution on click", () => {
    render(
      <ContentHotspotPreview
        content={[hotspot]}
        temporalDistribution={temporal}
        insufficientData={false}
      />,
    );
    const trigger = screen.getByRole("button", { name: /Affect hotspot/ });

    expect(
      screen.queryByText("Where confusion peaks in this section"),
    ).toBeNull();

    fireEvent.click(trigger);
    expect(
      screen.getByText("Where confusion peaks in this section"),
    ).toBeInTheDocument();

    fireEvent.click(trigger);
    expect(
      screen.queryByText("Where confusion peaks in this section"),
    ).toBeNull();
  });

  it("shows 'No temporal data available' when bins are empty/all-zero", () => {
    render(
      <ContentHotspotPreview
        content={[hotspot]}
        temporalDistribution={[]}
        insufficientData={false}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Affect hotspot/ }));
    expect(screen.getByText("No temporal data available")).toBeInTheDocument();
  });

  it("shows the exact no-issues copy when no block is a hotspot", () => {
    render(
      <ContentHotspotPreview
        content={[calm]}
        temporalDistribution={temporal}
        insufficientData={false}
      />,
    );
    expect(
      screen.getByText("No significant affect issues detected"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders content normally + no-issues copy when insufficientData is true", () => {
    render(
      <ContentHotspotPreview
        content={[hotspot]}
        temporalDistribution={temporal}
        insufficientData
      />,
    );
    // Even a would-be hotspot is not highlighted when data is insufficient.
    expect(screen.queryByRole("button")).toBeNull();
    expect(
      screen.getByText("No significant affect issues detected"),
    ).toBeInTheDocument();
  });
});
