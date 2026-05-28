import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AssessmentResults } from "./AssessmentResults";
import type { AttemptResult } from "@/types/assessment";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const makeResult = (overrides: Partial<AttemptResult> = {}): AttemptResult => ({
  id: "attempt1",
  score: 3,
  maxScore: 5,
  submittedAt: "2024-01-01T00:00:00Z",
  preScore: null,
  preMaxScore: null,
  questions: [
    {
      id: "q1",
      text: "What is 2+2?",
      sortOrder: 1,
      explanation: null,
      isCorrect: true,
      selectedOptionId: "o2",
      options: [
        { id: "o1", text: "3", sortOrder: 1, isCorrect: false },
        { id: "o2", text: "4", sortOrder: 2, isCorrect: true },
      ],
    },
    {
      id: "q2",
      text: "What is 2+3?",
      sortOrder: 2,
      explanation: "2 plus 3 equals 5.",
      isCorrect: false,
      selectedOptionId: "o3",
      options: [
        { id: "o3", text: "4", sortOrder: 1, isCorrect: false },
        { id: "o4", text: "5", sortOrder: 2, isCorrect: true },
      ],
    },
  ],
  ...overrides,
});

describe("AssessmentResults", () => {
  describe("score banner", () => {
    it("shows the score banner with correct score text", () => {
      render(
        <AssessmentResults
          result={makeResult()}
          type="pre"
          moduleId="m1"
          courseId="c1"
          firstLessonUrl="/courses/c1/modules/m1/lessons/l1"
        />
      );
      expect(screen.getByText("You got 3 out of 5 right")).toBeInTheDocument();
    });

    it("score banner has aria-live='polite'", () => {
      render(
        <AssessmentResults
          result={makeResult()}
          type="pre"
          moduleId="m1"
          courseId="c1"
          firstLessonUrl="/courses/c1/modules/m1/lessons/l1"
        />
      );
      const banner = screen.getByText("You got 3 out of 5 right").closest("[aria-live]");
      expect(banner).toHaveAttribute("aria-live", "polite");
    });

    it("does not show comparison text for pre type", () => {
      render(
        <AssessmentResults
          result={makeResult({ preScore: 1, preMaxScore: 5 })}
          type="pre"
          moduleId="m1"
          courseId="c1"
        />
      );
      expect(screen.queryByText(/You started at/)).not.toBeInTheDocument();
    });

    it("does not show comparison text for post type when preScore is null", () => {
      render(
        <AssessmentResults
          result={makeResult({ preScore: null, preMaxScore: null })}
          type="post"
          moduleId="m1"
          courseId="c1"
        />
      );
      expect(screen.queryByText(/You started at/)).not.toBeInTheDocument();
    });

    it("shows comparison text for post type when preScore is provided", () => {
      render(
        <AssessmentResults
          result={makeResult({ preScore: 2, preMaxScore: 5 })}
          type="post"
          moduleId="m1"
          courseId="c1"
        />
      );
      expect(
        screen.getByText("You started at 2/5 and finished at 3/5")
      ).toBeInTheDocument();
    });
  });

  describe("navigation links", () => {
    it("shows 'Continue to module' link for pre type with firstLessonUrl", () => {
      render(
        <AssessmentResults
          result={makeResult()}
          type="pre"
          moduleId="m1"
          courseId="c1"
          firstLessonUrl="/courses/c1/modules/m1/lessons/l1"
        />
      );
      const link = screen.getByRole("link", { name: "Continue to module" });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute("href", "/courses/c1/modules/m1/lessons/l1");
    });

    it("shows 'See your progress' link for post type", () => {
      render(
        <AssessmentResults
          result={makeResult()}
          type="post"
          moduleId="m1"
          courseId="c1"
        />
      );
      const link = screen.getByRole("link", { name: "See your progress" });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute("href", "/courses/c1");
    });

    it("shows 'See your progress' link for pre type without firstLessonUrl", () => {
      render(
        <AssessmentResults
          result={makeResult()}
          type="pre"
          moduleId="m1"
          courseId="c1"
        />
      );
      const link = screen.getByRole("link", { name: "See your progress" });
      expect(link).toHaveAttribute("href", "/courses/c1");
    });

    it("'See your progress' link uses the courseId in the URL", () => {
      render(
        <AssessmentResults
          result={makeResult()}
          type="post"
          moduleId="m1"
          courseId="course-xyz"
        />
      );
      expect(screen.getByRole("link", { name: "See your progress" })).toHaveAttribute(
        "href",
        "/courses/course-xyz"
      );
    });
  });

  describe("question results", () => {
    it("renders question text for each question", () => {
      render(
        <AssessmentResults
          result={makeResult()}
          type="pre"
          moduleId="m1"
          courseId="c1"
          firstLessonUrl="/first"
        />
      );
      expect(screen.getByText("1. What is 2+2?")).toBeInTheDocument();
      expect(screen.getByText("2. What is 2+3?")).toBeInTheDocument();
    });

    it("shows explanation for incorrect question", () => {
      render(
        <AssessmentResults
          result={makeResult()}
          type="pre"
          moduleId="m1"
          courseId="c1"
          firstLessonUrl="/first"
        />
      );
      expect(screen.getByText("2 plus 3 equals 5.")).toBeInTheDocument();
    });

    it("does not show explanation for correct question", () => {
      const result = makeResult();
      // q1 is correct and has no explanation (null)
      render(
        <AssessmentResults
          result={result}
          type="pre"
          moduleId="m1"
          courseId="c1"
          firstLessonUrl="/first"
        />
      );
      // The correct question's options text should appear but no extra explanation
      expect(screen.queryByText("2 + 2 equals 4.")).not.toBeInTheDocument();
    });

    it("sorts questions by sortOrder", () => {
      const result = makeResult({
        questions: [
          {
            id: "q2",
            text: "Second",
            sortOrder: 2,
            explanation: null,
            isCorrect: true,
            selectedOptionId: "o4",
            options: [{ id: "o4", text: "Correct", sortOrder: 1, isCorrect: true }],
          },
          {
            id: "q1",
            text: "First",
            sortOrder: 1,
            explanation: null,
            isCorrect: true,
            selectedOptionId: "o1",
            options: [{ id: "o1", text: "Yes", sortOrder: 1, isCorrect: true }],
          },
        ],
      });

      render(
        <AssessmentResults
          result={result}
          type="pre"
          moduleId="m1"
          courseId="c1"
          firstLessonUrl="/first"
        />
      );

      // First rendered question should have index 0 → "1."
      expect(screen.getByText("1. First")).toBeInTheDocument();
      expect(screen.getByText("2. Second")).toBeInTheDocument();
    });

    it("does not show explanation for incorrect question with null explanation", () => {
      const result = makeResult({
        questions: [
          {
            id: "q1",
            text: "A question without any hint",
            sortOrder: 1,
            explanation: null,
            isCorrect: false,
            selectedOptionId: "o1",
            options: [
              { id: "o1", text: "Wrong answer", sortOrder: 1, isCorrect: false },
              { id: "o2", text: "Right answer", sortOrder: 2, isCorrect: true },
            ],
          },
        ],
      });

      render(
        <AssessmentResults
          result={result}
          type="pre"
          moduleId="m1"
          courseId="c1"
          firstLessonUrl="/first"
        />
      );

      // The wrong option should appear but no explanation paragraph below it
      expect(screen.getByText("Wrong answer")).toBeInTheDocument();
      // Verify the options are rendered but no extra text beyond option texts appears
      expect(screen.queryByText("2 plus 3 equals 5.")).not.toBeInTheDocument();
    });
  });
});
