/**
 * Tests for the Affect Heatmap Grid (Story 7.3, AC1/AC2/AC3/AC4/AC6/AC7).
 *
 * Covers: role=grid + aria-label; rows × four affect columns with correct % text;
 * per-cell affect color class + aria-label; the low-confidence "Limited data"
 * badge; row click and Enter-key activation navigate to the section-detail route.
 * `next/navigation` `useRouter` is mocked to assert navigation.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

import type { HeatmapSectionRow } from "@/types/analytics";
import { AffectHeatmapGrid } from "./AffectHeatmapGrid";

const sections: HeatmapSectionRow[] = [
  {
    sectionId: "sec-1",
    sectionTitle: "Introduction",
    engagedPct: 80,
    confusedPct: 10,
    boredPct: 5,
    frustratedPct: 2,
    sampleCount: 120,
    confidence: "high",
    insufficientData: false,
  },
  {
    sectionId: "sec-2",
    sectionTitle: "Subnetting Deep Dive",
    engagedPct: 30,
    confusedPct: 68,
    boredPct: 12,
    frustratedPct: 41,
    sampleCount: 4,
    confidence: "low",
    insufficientData: true,
  },
];

describe("AffectHeatmapGrid", () => {
  beforeEach(() => {
    push.mockReset();
  });

  it("renders a grid with the accessible name", () => {
    render(<AffectHeatmapGrid courseId="course-1" sections={sections} />);
    expect(
      screen.getByRole("grid", { name: "Affect distribution by section" }),
    ).toBeInTheDocument();
  });

  it("renders the four affect column headers in order", () => {
    render(<AffectHeatmapGrid courseId="course-1" sections={sections} />);
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Section", "Engaged", "Confused", "Bored", "Frustrated"]);
  });

  it("renders one row per section with its title", () => {
    render(<AffectHeatmapGrid courseId="course-1" sections={sections} />);
    expect(screen.getByText("Introduction")).toBeInTheDocument();
    expect(screen.getByText("Subnetting Deep Dive")).toBeInTheDocument();
    // 4 cells per section row.
    expect(screen.getAllByRole("gridcell")).toHaveLength(sections.length * 4);
  });

  it("shows the rounded percentage in each cell with a per-cell aria-label", () => {
    render(<AffectHeatmapGrid courseId="course-1" sections={sections} />);
    const cell = screen.getByLabelText("Subnetting Deep Dive — Confused 68%");
    expect(cell).toHaveTextContent("68%");
  });

  it("color-codes each cell with its column affect-color class", () => {
    render(<AffectHeatmapGrid courseId="course-1" sections={sections} />);
    // Engaged 80% on row 1 → bold band of the engaged token.
    const engaged = screen.getByLabelText("Introduction — Engaged 80%");
    expect(engaged.className).toContain("bg-affect-engaged/100");
    // Confused 68% → bold confused; Bored 5% → light bored.
    expect(
      screen.getByLabelText("Subnetting Deep Dive — Confused 68%").className,
    ).toContain("bg-affect-confused/100");
    expect(
      screen.getByLabelText("Introduction — Bored 5%").className,
    ).toContain("bg-affect-bored/15");
  });

  it("renders a 'Limited data' badge on a low-confidence / insufficient-data row", () => {
    render(<AffectHeatmapGrid courseId="course-1" sections={sections} />);
    const rows = screen.getAllByRole("row");
    // rows[0] is the header; the second section row carries the low-confidence flag.
    const limitedRow = rows.find((r) =>
      within(r).queryByText("Subnetting Deep Dive"),
    )!;
    expect(within(limitedRow).getByText("Limited data")).toBeInTheDocument();
  });

  it("navigates to the section detail route on row click", () => {
    render(<AffectHeatmapGrid courseId="course-1" sections={sections} />);
    fireEvent.click(screen.getByText("Introduction"));
    expect(push).toHaveBeenCalledWith("/analytics/course-1/sections/sec-1");
  });

  it("activates the focused row with Enter (keyboard navigation)", () => {
    render(<AffectHeatmapGrid courseId="course-1" sections={sections} />);
    const rows = screen.getAllByRole("row");
    const secondRow = rows.find((r) =>
      within(r).queryByText("Subnetting Deep Dive"),
    )!;
    fireEvent.keyDown(secondRow, { key: "Enter" });
    expect(push).toHaveBeenCalledWith("/analytics/course-1/sections/sec-2");
  });
});
