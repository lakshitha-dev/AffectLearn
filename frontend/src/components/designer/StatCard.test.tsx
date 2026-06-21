import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { StatCard } from "./StatCard";

describe("StatCard", () => {
  it("renders the label and value", () => {
    render(<StatCard label="Total Learners" value="42" />);
    expect(screen.getByText("Total Learners")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders the supporting indicator", () => {
    render(
      <StatCard
        label="Completion Rate"
        value="72%"
        indicator="120 samples · high confidence"
        confidence="high"
      />,
    );
    expect(
      screen.getByText("120 samples · high confidence"),
    ).toBeInTheDocument();
  });

  it("shows the 'Limited data' badge when insufficientData", () => {
    render(<StatCard label="Avg Engagement" value="50%" insufficientData />);
    expect(screen.getByText("Limited data")).toBeInTheDocument();
  });

  it("shows the 'Limited data' badge for low confidence", () => {
    render(<StatCard label="Avg Engagement" value="50%" confidence="low" />);
    expect(screen.getByText("Limited data")).toBeInTheDocument();
  });

  it("does NOT show the badge for high confidence and sufficient data", () => {
    render(
      <StatCard
        label="Avg Engagement"
        value="80%"
        confidence="high"
        insufficientData={false}
      />,
    );
    expect(screen.queryByText("Limited data")).not.toBeInTheDocument();
  });
});
