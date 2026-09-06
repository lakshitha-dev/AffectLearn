/**
 * Tests for the content-effectiveness panel.
 *
 * The behaviour worth pinning is the treatment of NULL. Zero and unknown are different facts:
 * a section where no help was offered and one where help was offered but never followed by an
 * attempt both have "no outcome rate". Rendering both as 0% would tell a designer that help
 * never works in a section where help was simply never given — and they would rewrite it.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";

vi.mock("@/hooks/use-analytics", () => ({
  useCourseEffectiveness: vi.fn(),
  useStruggleLeaderboard: vi.fn(),
}));

import { useCourseEffectiveness, useStruggleLeaderboard } from "@/hooks/use-analytics";
import { ContentEffectiveness } from "./ContentEffectiveness";
import type { SectionEffectivenessRow } from "@/types/analytics";

const mockEffectiveness = useCourseEffectiveness as ReturnType<typeof vi.fn>;
const mockStruggle = useStruggleLeaderboard as ReturnType<typeof vi.fn>;

function row(overrides: Partial<SectionEffectivenessRow> = {}): SectionEffectivenessRow {
  return {
    sectionId: "sec-1",
    sectionTitle: "Pointers",
    observedLearners: 12,
    timeOnSectionS: 200,
    timePer100Words: 40,
    backNavCount: 1,
    quizAttemptCount: 2,
    quizIncorrectCount: 1,
    quizResponseTimeMsMean: 5000,
    showAnswerUsedRate: 25,
    revisitRate: 50,
    quizIncorrectRate: 40,
    assistance: {
      offers: 6,
      learnersHelped: 4,
      dismissalRate: 20,
      generatedRate: 0,
      followedByCorrectRate: 75,
      outcomesRecorded: 4,
    },
    confidence: "high",
    insufficientData: false,
    ...overrides,
  };
}

function mount(sections: SectionEffectivenessRow[], struggle: unknown[] = []) {
  mockEffectiveness.mockReturnValue({
    data: { courseId: "c1", sections },
    isPending: false,
    isError: false,
    refetch: vi.fn(),
  });
  mockStruggle.mockReturnValue({
    data: { courseId: "c1", sections: struggle },
    isPending: false,
    isError: false,
  });
  render(<ContentEffectiveness courseId="c1" />);
}

beforeEach(() => {
  mockEffectiveness.mockReset();
  mockStruggle.mockReset();
});

describe("ContentEffectiveness", () => {
  it("shows the behavioural figures for a section", () => {
    mount([row()]);

    const line = screen.getByRole("row", { name: /Pointers/ });
    expect(within(line).getByText("50%")).toBeInTheDocument();
    expect(within(line).getByText("25%")).toBeInTheDocument();
  });

  it("renders an unknown rate as a dash, never as zero", () => {
    // The whole point. A section where help was never offered has no outcome rate; showing 0%
    // would say the help failed.
    mount([
      row({
        assistance: {
          offers: 0,
          learnersHelped: 0,
          dismissalRate: null,
          generatedRate: null,
          followedByCorrectRate: null,
          outcomesRecorded: 0,
        },
      }),
    ]);

    const line = screen.getByRole("row", { name: /Pointers/ });
    expect(within(line).getAllByText("—").length).toBeGreaterThan(0);
    expect(within(line).queryByText("0%")).not.toBeInTheDocument();
  });

  it("distinguishes a genuine zero from an unknown", () => {
    mount([row({ revisitRate: 0 })]);

    const line = screen.getByRole("row", { name: /Pointers/ });
    expect(within(line).getByText("0%")).toBeInTheDocument();
  });

  it("labels a thin sample rather than hiding the row", () => {
    // Seeing "2 learners" beside a number is how a designer knows not to act on it. Hiding the
    // row would leave them wondering whether the page was broken.
    mount([row({ observedLearners: 2, insufficientData: true })]);

    expect(screen.getByText("thin")).toBeInTheDocument();
    expect(screen.getByText("Pointers")).toBeInTheDocument();
  });

  it("does not label a healthy sample", () => {
    mount([row({ observedLearners: 40, insufficientData: false })]);
    expect(screen.queryByText("thin")).not.toBeInTheDocument();
  });

  it("says the outcome figure is an association, not a cause", () => {
    // The surface built on this data is exactly where the causal reading creeps in, so the
    // caveat is part of the component rather than left to the reader.
    mount([row()]);

    expect(
      screen.getByText(/not that the help caused it/i),
    ).toBeInTheDocument();
  });

  it("reports the denominator behind the outcome rate", () => {
    mount([row()]);
    expect(screen.getByText(/of 4/)).toBeInTheDocument();
  });

  it("shows an empty state when nothing has been completed", () => {
    mount([row({ observedLearners: 0 })]);

    expect(screen.getByText(/No completions recorded yet/i)).toBeInTheDocument();
    expect(screen.getByText(/Nothing is estimated before then/i)).toBeInTheDocument();
  });

  it("lists the hardest sections when there are enough observations", () => {
    mount([row()], [{ ...row(), struggleScore: 115 }]);

    expect(screen.getByText("Hardest sections")).toBeInTheDocument();
    expect(screen.getByText(/left out rather than ranked low/i)).toBeInTheDocument();
  });

  it("omits the leaderboard when nothing clears the sample threshold", () => {
    mount([row()], []);
    expect(screen.queryByText("Hardest sections")).not.toBeInTheDocument();
  });
});
