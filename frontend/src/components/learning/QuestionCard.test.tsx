import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QuestionCard } from "./QuestionCard";
import type { AssessmentQuestion } from "@/types/assessment";

const question: AssessmentQuestion = {
  id: "q1",
  text: "What is the capital of France?",
  sortOrder: 1,
  options: [
    { id: "o1", text: "Berlin", sortOrder: 1 },
    { id: "o2", text: "Paris", sortOrder: 2 },
    { id: "o3", text: "Madrid", sortOrder: 3 },
  ],
};

const question2: AssessmentQuestion = {
  id: "q2",
  text: "Which language runs in the browser?",
  sortOrder: 2,
  options: [
    { id: "o4", text: "Python", sortOrder: 1 },
    { id: "o5", text: "JavaScript", sortOrder: 2 },
  ],
};

describe("QuestionCard", () => {
  let onSelect: Mock<(questionId: string, optionId: string) => void>;

  beforeEach(() => {
    onSelect = vi.fn();
  });

  describe("rendering", () => {
    it("displays the question text with 1-based index prefix", () => {
      render(
        <QuestionCard
          question={question}
          selectedOptionId={undefined}
          onSelect={onSelect}
          index={0}
        />
      );
      expect(screen.getByText("1. What is the capital of France?")).toBeInTheDocument();
    });

    it("uses index+1 for the question prefix (index=2 shows '3.')", () => {
      render(
        <QuestionCard
          question={question2}
          selectedOptionId={undefined}
          onSelect={onSelect}
          index={2}
        />
      );
      expect(screen.getByText("3. Which language runs in the browser?")).toBeInTheDocument();
    });

    it("renders all option texts", () => {
      render(
        <QuestionCard
          question={question}
          selectedOptionId={undefined}
          onSelect={onSelect}
          index={0}
        />
      );
      expect(screen.getByText("Berlin")).toBeInTheDocument();
      expect(screen.getByText("Paris")).toBeInTheDocument();
      expect(screen.getByText("Madrid")).toBeInTheDocument();
    });

    it("renders a radiogroup container", () => {
      render(
        <QuestionCard
          question={question}
          selectedOptionId={undefined}
          onSelect={onSelect}
          index={0}
        />
      );
      expect(screen.getByRole("radiogroup")).toBeInTheDocument();
    });

    it("radiogroup is labelled by the question text element", () => {
      render(
        <QuestionCard
          question={question}
          selectedOptionId={undefined}
          onSelect={onSelect}
          index={0}
        />
      );
      const radiogroup = screen.getByRole("radiogroup");
      expect(radiogroup).toHaveAttribute("aria-labelledby", `question-${question.id}`);
    });

    it("renders each option as a radio button", () => {
      render(
        <QuestionCard
          question={question}
          selectedOptionId={undefined}
          onSelect={onSelect}
          index={0}
        />
      );
      const radios = screen.getAllByRole("radio");
      expect(radios).toHaveLength(3);
    });

    it("all options are unchecked when no selectedOptionId", () => {
      render(
        <QuestionCard
          question={question}
          selectedOptionId={undefined}
          onSelect={onSelect}
          index={0}
        />
      );
      screen.getAllByRole("radio").forEach((r) =>
        expect(r).toHaveAttribute("aria-checked", "false")
      );
    });
  });

  describe("selected option", () => {
    it("marks the matching option as checked", () => {
      render(
        <QuestionCard
          question={question}
          selectedOptionId="o2"
          onSelect={onSelect}
          index={0}
        />
      );
      const paris = screen.getByRole("radio", { name: "Paris" });
      expect(paris).toHaveAttribute("aria-checked", "true");
    });

    it("other options remain unchecked when one is selected", () => {
      render(
        <QuestionCard
          question={question}
          selectedOptionId="o2"
          onSelect={onSelect}
          index={0}
        />
      );
      expect(screen.getByRole("radio", { name: "Berlin" })).toHaveAttribute("aria-checked", "false");
      expect(screen.getByRole("radio", { name: "Madrid" })).toHaveAttribute("aria-checked", "false");
    });
  });

  describe("interaction", () => {
    it("calls onSelect with questionId and optionId when an option is clicked", () => {
      render(
        <QuestionCard
          question={question}
          selectedOptionId={undefined}
          onSelect={onSelect}
          index={0}
        />
      );
      fireEvent.click(screen.getByRole("radio", { name: "Paris" }));
      expect(onSelect).toHaveBeenCalledWith("q1", "o2");
    });

    it("calls onSelect with the correct questionId when clicking a different question", () => {
      render(
        <QuestionCard
          question={question2}
          selectedOptionId={undefined}
          onSelect={onSelect}
          index={1}
        />
      );
      fireEvent.click(screen.getByRole("radio", { name: "JavaScript" }));
      expect(onSelect).toHaveBeenCalledWith("q2", "o5");
    });

    it("calls onSelect each time an option is clicked", () => {
      render(
        <QuestionCard
          question={question}
          selectedOptionId={undefined}
          onSelect={onSelect}
          index={0}
        />
      );
      fireEvent.click(screen.getByRole("radio", { name: "Berlin" }));
      fireEvent.click(screen.getByRole("radio", { name: "Madrid" }));
      expect(onSelect).toHaveBeenCalledTimes(2);
    });

    it("calls onSelect even when clicking the currently selected option", () => {
      render(
        <QuestionCard
          question={question}
          selectedOptionId="o2"
          onSelect={onSelect}
          index={0}
        />
      );
      fireEvent.click(screen.getByRole("radio", { name: "Paris" }));
      expect(onSelect).toHaveBeenCalledWith("q1", "o2");
    });
  });
});
