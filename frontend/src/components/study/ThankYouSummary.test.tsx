import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";

import { ThankYouSummary } from "./ThankYouSummary";
import type { LearnerProgressResponse } from "@/types/progress";

vi.mock("@/hooks/use-progress", () => ({
  useLearnerProgress: vi.fn(),
}));

import { useLearnerProgress } from "@/hooks/use-progress";

const mockUseLearnerProgress = vi.mocked(useLearnerProgress);

type HookReturn = ReturnType<typeof useLearnerProgress>;

function mockResult(over: Partial<HookReturn>): HookReturn {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    ...over,
  } as HookReturn;
}

const progress: LearnerProgressResponse = {
  courses: [
    {
      courseId: "c1",
      courseTitle: "React Fundamentals",
      totalSections: 12,
      completedSections: 12,
      percentage: 100,
    },
    {
      courseId: "c2",
      courseTitle: "Advanced Patterns",
      totalSections: 8,
      completedSections: 4,
      percentage: 50,
    },
  ],
  sections: [],
  quizzes: { answered: 10, correct: 8 },
};

describe("ThankYouSummary", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the warm Thank you heading", () => {
    mockUseLearnerProgress.mockReturnValue(mockResult({ data: progress }));
    render(<ThankYouSummary learnerId="u1" />);
    expect(screen.getByRole("heading", { name: /Thank you/i })).toBeInTheDocument();
  });

  it("renders modules/sections completed and overall progress %", () => {
    mockUseLearnerProgress.mockReturnValue(mockResult({ data: progress }));
    render(<ThankYouSummary learnerId="u1" />);
    // 16 of 20 sections completed across the two courses → 80%.
    expect(screen.getByText("16 / 20")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
    // Per-course rows.
    expect(screen.getByText("React Fundamentals")).toBeInTheDocument();
    expect(screen.getByText(/12\/12 sections · 100%/)).toBeInTheDocument();
    expect(screen.getByText("Advanced Patterns")).toBeInTheDocument();
    // Quiz tally.
    expect(screen.getByText("8 / 10")).toBeInTheDocument();
  });

  it("shows a loading state while progress is fetching", () => {
    mockUseLearnerProgress.mockReturnValue(mockResult({ isLoading: true }));
    render(<ThankYouSummary learnerId="u1" />);
    expect(screen.getByText(/Loading your achievements/i)).toBeInTheDocument();
  });

  it("is empty-safe when progress is unavailable", () => {
    mockUseLearnerProgress.mockReturnValue(mockResult({ isError: true }));
    render(<ThankYouSummary learnerId="u1" />);
    expect(screen.getByRole("heading", { name: /Thank you/i })).toBeInTheDocument();
    expect(
      screen.getByText(/achievements summary isn't available right now/i),
    ).toBeInTheDocument();
  });
});
