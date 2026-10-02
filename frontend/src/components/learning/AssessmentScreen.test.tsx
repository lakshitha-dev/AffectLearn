import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AssessmentScreen } from "./AssessmentScreen";
import type { AnswerPayload, Assessment } from "@/types/assessment";

const twoQuestionAssessment: Assessment = {
  id: "a1",
  moduleId: "m1",
  assessmentType: "pre",
  title: "Pre-assessment",
  questions: [
    {
      id: "q1",
      text: "First question",
      sortOrder: 1,
      options: [
        { id: "o1", text: "Option A", sortOrder: 1 },
        { id: "o2", text: "Option B", sortOrder: 2 },
      ],
    },
    {
      id: "q2",
      text: "Second question",
      sortOrder: 2,
      options: [
        { id: "o3", text: "Option C", sortOrder: 1 },
        { id: "o4", text: "Option D", sortOrder: 2 },
      ],
    },
  ],
};

const singleQuestionAssessment: Assessment = {
  id: "a2",
  moduleId: "m1",
  assessmentType: "post",
  title: "Post-assessment",
  questions: [
    {
      id: "q3",
      text: "Only question",
      sortOrder: 1,
      options: [
        { id: "o5", text: "Yes", sortOrder: 1 },
        { id: "o6", text: "No", sortOrder: 2 },
      ],
    },
  ],
};

describe("AssessmentScreen", () => {
  let onSubmit: Mock<(answers: AnswerPayload[]) => void>;

  beforeEach(() => {
    onSubmit = vi.fn();
  });

  describe("heading and subtext", () => {
    it("shows pre-assessment heading for type='pre'", () => {
      render(
        <AssessmentScreen
          assessment={twoQuestionAssessment}
          type="pre"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );
      expect(screen.getByText("Let's see where you're starting from")).toBeInTheDocument();
    });

    it("shows post-assessment heading for type='post'", () => {
      render(
        <AssessmentScreen
          assessment={singleQuestionAssessment}
          type="post"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );
      expect(screen.getByText("Let's see how much you've learned")).toBeInTheDocument();
    });

    it("shows pre-assessment subtext for type='pre'", () => {
      render(
        <AssessmentScreen
          assessment={twoQuestionAssessment}
          type="pre"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );
      expect(
        screen.getByText("This isn't graded — it just helps us understand where you're starting")
      ).toBeInTheDocument();
    });

    it("shows post-assessment subtext for type='post'", () => {
      render(
        <AssessmentScreen
          assessment={singleQuestionAssessment}
          type="post"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );
      expect(screen.getByText("Answer all questions to see your results")).toBeInTheDocument();
    });
  });

  describe("answered counter", () => {
    it("shows '0 of N answered' initially", () => {
      render(
        <AssessmentScreen
          assessment={twoQuestionAssessment}
          type="pre"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );
      expect(screen.getByText("0 of 2 answered")).toBeInTheDocument();
    });

    it("increments counter as questions are answered", () => {
      render(
        <AssessmentScreen
          assessment={twoQuestionAssessment}
          type="pre"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );
      fireEvent.click(screen.getByRole("radio", { name: "Option A" }));
      expect(screen.getByText("1 of 2 answered")).toBeInTheDocument();
    });

    it("shows 'N of N answered' when all questions answered", () => {
      render(
        <AssessmentScreen
          assessment={twoQuestionAssessment}
          type="pre"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );
      fireEvent.click(screen.getByRole("radio", { name: "Option A" }));
      fireEvent.click(screen.getByRole("radio", { name: "Option C" }));
      expect(screen.getByText("2 of 2 answered")).toBeInTheDocument();
    });
  });

  describe("submit button", () => {
    it("shows 'Answer all questions to continue' when not all answered", () => {
      render(
        <AssessmentScreen
          assessment={twoQuestionAssessment}
          type="pre"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );
      expect(
        screen.getByRole("button", { name: "Answer all questions to continue" })
      ).toBeInTheDocument();
    });

    it("submit button is disabled when not all questions answered", () => {
      render(
        <AssessmentScreen
          assessment={twoQuestionAssessment}
          type="pre"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );
      expect(
        screen.getByRole("button", { name: "Answer all questions to continue" })
      ).toBeDisabled();
    });

    it("submit button has aria-disabled=true when not all answered", () => {
      render(
        <AssessmentScreen
          assessment={twoQuestionAssessment}
          type="pre"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );
      const btn = screen.getByRole("button", { name: "Answer all questions to continue" });
      expect(btn).toHaveAttribute("aria-disabled", "true");
    });

    it("changes label to 'Submit assessment' when all questions answered", () => {
      render(
        <AssessmentScreen
          assessment={twoQuestionAssessment}
          type="pre"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );
      fireEvent.click(screen.getByRole("radio", { name: "Option A" }));
      fireEvent.click(screen.getByRole("radio", { name: "Option C" }));
      expect(screen.getByRole("button", { name: "Submit assessment" })).toBeInTheDocument();
    });

    it("submit button is enabled when all questions answered", () => {
      render(
        <AssessmentScreen
          assessment={twoQuestionAssessment}
          type="pre"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );
      fireEvent.click(screen.getByRole("radio", { name: "Option A" }));
      fireEvent.click(screen.getByRole("radio", { name: "Option C" }));
      expect(screen.getByRole("button", { name: "Submit assessment" })).not.toBeDisabled();
    });

    it("submit button has aria-disabled=false when all answered", () => {
      render(
        <AssessmentScreen
          assessment={twoQuestionAssessment}
          type="pre"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );
      fireEvent.click(screen.getByRole("radio", { name: "Option A" }));
      fireEvent.click(screen.getByRole("radio", { name: "Option C" }));
      expect(screen.getByRole("button", { name: "Submit assessment" })).toHaveAttribute(
        "aria-disabled",
        "false"
      );
    });

    it("shows 'Submitting…' when isSubmitting=true", () => {
      render(
        <AssessmentScreen
          assessment={singleQuestionAssessment}
          type="post"
          onSubmit={onSubmit}
          isSubmitting={true}
        />
      );
      // Even with all answered, submitting state takes precedence
      expect(screen.getByText("Submitting…")).toBeInTheDocument();
    });

    it("is disabled when isSubmitting=true even if all answered", () => {
      render(
        <AssessmentScreen
          assessment={singleQuestionAssessment}
          type="post"
          onSubmit={onSubmit}
          isSubmitting={true}
        />
      );
      fireEvent.click(screen.getByRole("radio", { name: "Yes" }));
      expect(screen.getByRole("button", { name: "Submitting…" })).toBeDisabled();
    });
  });

  describe("submission", () => {
    it("calls onSubmit with AnswerPayload[] when submitted", () => {
      render(
        <AssessmentScreen
          assessment={twoQuestionAssessment}
          type="pre"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );
      fireEvent.click(screen.getByRole("radio", { name: "Option A" }));
      fireEvent.click(screen.getByRole("radio", { name: "Option C" }));
      fireEvent.click(screen.getByRole("button", { name: "Submit assessment" }));

      expect(onSubmit).toHaveBeenCalledTimes(1);
      const payload = onSubmit.mock.calls[0][0];
      expect(payload).toHaveLength(2);
      expect(payload).toEqual(
        expect.arrayContaining([
          { questionId: "q1", selectedOptionId: "o1" },
          { questionId: "q2", selectedOptionId: "o3" },
        ])
      );
    });

    it("changing an answer updates the payload", () => {
      render(
        <AssessmentScreen
          assessment={twoQuestionAssessment}
          type="pre"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );
      fireEvent.click(screen.getByRole("radio", { name: "Option A" }));
      fireEvent.click(screen.getByRole("radio", { name: "Option B" }));
      fireEvent.click(screen.getByRole("radio", { name: "Option C" }));
      fireEvent.click(screen.getByRole("button", { name: "Submit assessment" }));

      const payload = onSubmit.mock.calls[0][0];
      const q1Answer = payload.find((p: { questionId: string }) => p.questionId === "q1");
      expect(q1Answer?.selectedOptionId).toBe("o2");
    });
  });

  describe("question ordering", () => {
    it("sorts questions by sortOrder before rendering", () => {
      const reversedAssessment: Assessment = {
        ...twoQuestionAssessment,
        questions: [
          { ...twoQuestionAssessment.questions[1] }, // sortOrder: 2
          { ...twoQuestionAssessment.questions[0] }, // sortOrder: 1
        ],
      };

      render(
        <AssessmentScreen
          assessment={reversedAssessment}
          type="pre"
          onSubmit={onSubmit}
          isSubmitting={false}
        />
      );

      const questionTexts = screen.getAllByRole("radiogroup");
      // First radiogroup should correspond to the question with sortOrder=1
      expect(questionTexts[0]).toHaveAttribute("aria-labelledby", "question-q1");
    });
  });
});
