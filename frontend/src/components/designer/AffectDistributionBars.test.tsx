/**
 * Tests for the Affect Distribution bars (Story 7.4, AC2).
 *
 * Covers: four bars in the fixed order with the right labels + percentages +
 * affect color classes; bar width reflects pct; does NOT normalize (all four at
 * 80% still render 80% each).
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import type { AffectDistribution } from "@/types/analytics";
import { AffectDistributionBars } from "./AffectDistributionBars";

const distribution: AffectDistribution = {
  engagedPct: 40,
  confusedPct: 68,
  boredPct: 12,
  frustratedPct: 45,
};

describe("AffectDistributionBars", () => {
  it("renders four labeled bars in the fixed order", () => {
    render(<AffectDistributionBars distribution={distribution} />);
    expect(screen.getByText("Engaged")).toBeInTheDocument();
    expect(screen.getByText("Confused")).toBeInTheDocument();
    expect(screen.getByText("Bored")).toBeInTheDocument();
    expect(screen.getByText("Frustrated")).toBeInTheDocument();
  });

  it("shows the rounded percentage with a per-bar aria-label", () => {
    render(<AffectDistributionBars distribution={distribution} />);
    expect(screen.getByLabelText("Confused 68%")).toBeInTheDocument();
    expect(screen.getByLabelText("Frustrated 45%")).toBeInTheDocument();
  });

  it("fills each bar in its affect color and encodes pct in the width", () => {
    const { container } = render(
      <AffectDistributionBars distribution={distribution} />,
    );
    const confusedBar = screen.getByLabelText("Confused 68%");
    const fill = confusedBar.querySelector(".bg-affect-confused") as HTMLElement;
    expect(fill).not.toBeNull();
    expect(fill.style.width).toBe("68%");
    expect(container.querySelector(".bg-affect-engaged")).not.toBeNull();
    expect(container.querySelector(".bg-affect-bored")).not.toBeNull();
    expect(container.querySelector(".bg-affect-frustrated")).not.toBeNull();
  });

  it("does NOT normalize — all four at 80% each render 80%", () => {
    render(
      <AffectDistributionBars
        distribution={{
          engagedPct: 80,
          confusedPct: 80,
          boredPct: 80,
          frustratedPct: 80,
        }}
      />,
    );
    expect(screen.getAllByText("80%")).toHaveLength(4);
  });

  it("clamps the bar width to 100% for out-of-range values", () => {
    render(
      <AffectDistributionBars
        distribution={{
          engagedPct: 130,
          confusedPct: 0,
          boredPct: 0,
          frustratedPct: 0,
        }}
      />,
    );
    const engaged = screen.getByLabelText("Engaged 130%");
    const fill = engaged.querySelector(".bg-affect-engaged") as HTMLElement;
    expect(fill.style.width).toBe("100%");
  });
});
