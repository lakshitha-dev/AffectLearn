import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QuizBlock } from "./QuizBlock";

const singleContent = {
  question: "What is 2 + 2?",
  type: "single" as const,
  options: [
    { id: "a", text: "3", isCorrect: false },
    { id: "b", text: "4", isCorrect: true },
    { id: "c", text: "5", isCorrect: false },
  ],
  explanation: "2 + 2 equals 4.",
};

const multipleContent = {
  question: "Which are prime numbers?",
  type: "multiple" as const,
  options: [
    { id: "a", text: "2", isCorrect: true },
    { id: "b", text: "3", isCorrect: true },
    { id: "c", text: "4", isCorrect: false },
  ],
  explanation: "2 and 3 are prime.",
};

describe("QuizBlock", () => {
  describe("rendering", () => {
    it("renders the question text", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      expect(screen.getByText("What is 2 + 2?")).toBeInTheDocument();
    });

    it("renders all option texts", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      expect(screen.getByText("3")).toBeInTheDocument();
      expect(screen.getByText("4")).toBeInTheDocument();
      expect(screen.getByText("5")).toBeInTheDocument();
    });

    it("renders the Check answer button when not submitted", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      expect(screen.getByRole("button", { name: "Check answer" })).toBeInTheDocument();
    });

    it("uses radiogroup role for single-answer quiz", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      expect(screen.getByRole("radiogroup")).toBeInTheDocument();
    });

    it("uses group role for multiple-answer quiz", () => {
      render(<QuizBlock blockId="q1" content={multipleContent} />);
      expect(screen.getByRole("group")).toBeInTheDocument();
    });

    it("renders options as radio buttons for single-answer type", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      const radios = screen.getAllByRole("radio");
      expect(radios).toHaveLength(3);
    });

    it("renders options as checkboxes for multiple-answer type", () => {
      render(<QuizBlock blockId="q1" content={multipleContent} />);
      const checkboxes = screen.getAllByRole("checkbox");
      expect(checkboxes).toHaveLength(3);
    });

    it("all radio options are unchecked initially", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      const radios = screen.getAllByRole("radio");
      radios.forEach((r) => expect(r).toHaveAttribute("aria-checked", "false"));
    });
  });

  describe("submit button state", () => {
    it("submit button is disabled when nothing is selected", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      expect(screen.getByRole("button", { name: "Check answer" })).toBeDisabled();
    });

    it("submit button is enabled after selecting an option", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      fireEvent.click(screen.getByText("4"));
      expect(screen.getByRole("button", { name: "Check answer" })).not.toBeDisabled();
    });
  });

  describe("single-answer selection", () => {
    it("marks clicked option as checked", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      const option4 = screen.getByRole("radio", { name: /4/ });
      fireEvent.click(option4);
      expect(option4).toHaveAttribute("aria-checked", "true");
    });

    it("deselects previously selected option when a new one is clicked", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      const option3 = screen.getByRole("radio", { name: /3/ });
      const option4 = screen.getByRole("radio", { name: /4/ });

      fireEvent.click(option3);
      expect(option3).toHaveAttribute("aria-checked", "true");

      fireEvent.click(option4);
      expect(option3).toHaveAttribute("aria-checked", "false");
      expect(option4).toHaveAttribute("aria-checked", "true");
    });

    it("only one option can be selected at a time", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      fireEvent.click(screen.getByRole("radio", { name: /3/ }));
      fireEvent.click(screen.getByRole("radio", { name: /4/ }));

      const checked = screen.getAllByRole("radio").filter(
        (r) => r.getAttribute("aria-checked") === "true"
      );
      expect(checked).toHaveLength(1);
    });
  });

  describe("multiple-answer selection", () => {
    it("toggles options independently", () => {
      render(<QuizBlock blockId="q1" content={multipleContent} />);
      const option2 = screen.getByRole("checkbox", { name: /^2$/ });
      const option3 = screen.getByRole("checkbox", { name: /^3$/ });

      fireEvent.click(option2);
      fireEvent.click(option3);

      expect(option2).toHaveAttribute("aria-checked", "true");
      expect(option3).toHaveAttribute("aria-checked", "true");
    });

    it("deselects an option when clicked again", () => {
      render(<QuizBlock blockId="q1" content={multipleContent} />);
      const option2 = screen.getByRole("checkbox", { name: /^2$/ });

      fireEvent.click(option2);
      expect(option2).toHaveAttribute("aria-checked", "true");

      fireEvent.click(option2);
      expect(option2).toHaveAttribute("aria-checked", "false");
    });

    it("multiple options can be selected simultaneously", () => {
      render(<QuizBlock blockId="q1" content={multipleContent} />);
      fireEvent.click(screen.getByRole("checkbox", { name: /^2$/ }));
      fireEvent.click(screen.getByRole("checkbox", { name: /^3$/ }));

      const checked = screen.getAllByRole("checkbox").filter(
        (r) => r.getAttribute("aria-checked") === "true"
      );
      expect(checked).toHaveLength(2);
    });
  });

  describe("after correct submission", () => {
    it("calls onSubmit with correct arguments when answer is right", () => {
      const onSubmit = vi.fn();
      render(<QuizBlock blockId="q1" content={singleContent} onSubmit={onSubmit} />);

      fireEvent.click(screen.getByRole("radio", { name: /4/ }));
      fireEvent.click(screen.getByRole("button", { name: "Check answer" }));

      expect(onSubmit).toHaveBeenCalledWith("q1", ["b"], true);
    });

    it("shows 'Correct!' feedback", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      fireEvent.click(screen.getByRole("radio", { name: /4/ }));
      fireEvent.click(screen.getByRole("button", { name: "Check answer" }));

      expect(screen.getByText("Correct!")).toBeInTheDocument();
    });

    it("hides the Check answer button after submission", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      fireEvent.click(screen.getByRole("radio", { name: /4/ }));
      fireEvent.click(screen.getByRole("button", { name: "Check answer" }));

      expect(screen.queryByRole("button", { name: "Check answer" })).not.toBeInTheDocument();
    });

    it("does not show explanation when answer is correct", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      fireEvent.click(screen.getByRole("radio", { name: /4/ }));
      fireEvent.click(screen.getByRole("button", { name: "Check answer" }));

      expect(screen.queryByText("2 + 2 equals 4.")).not.toBeInTheDocument();
    });

    it("disables all option buttons after submission", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      fireEvent.click(screen.getByRole("radio", { name: /4/ }));
      fireEvent.click(screen.getByRole("button", { name: "Check answer" }));

      screen.getAllByRole("radio").forEach((r) => expect(r).toBeDisabled());
    });
  });

  describe("after incorrect submission", () => {
    it("calls onSubmit with isCorrect=false when answer is wrong", () => {
      const onSubmit = vi.fn();
      render(<QuizBlock blockId="q1" content={singleContent} onSubmit={onSubmit} />);

      fireEvent.click(screen.getByRole("radio", { name: /3/ }));
      fireEvent.click(screen.getByRole("button", { name: "Check answer" }));

      expect(onSubmit).toHaveBeenCalledWith("q1", ["a"], false);
    });

    it("shows 'Not quite' feedback", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      fireEvent.click(screen.getByRole("radio", { name: /3/ }));
      fireEvent.click(screen.getByRole("button", { name: "Check answer" }));

      expect(screen.getByText("Not quite")).toBeInTheDocument();
    });

    it("shows explanation when answer is incorrect and explanation exists", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      fireEvent.click(screen.getByRole("radio", { name: /3/ }));
      fireEvent.click(screen.getByRole("button", { name: "Check answer" }));

      expect(screen.getByText("2 + 2 equals 4.")).toBeInTheDocument();
    });

    it("does not show explanation when content has no explanation", () => {
      const contentNoExplanation = { ...singleContent, explanation: undefined };
      render(<QuizBlock blockId="q1" content={contentNoExplanation} />);
      fireEvent.click(screen.getByRole("radio", { name: /3/ }));
      fireEvent.click(screen.getByRole("button", { name: "Check answer" }));

      expect(screen.queryByText("2 + 2 equals 4.")).not.toBeInTheDocument();
    });
  });

  describe("multiple-answer correct submission", () => {
    it("calls onSubmit correctly when all correct options are selected", () => {
      const onSubmit = vi.fn();
      render(<QuizBlock blockId="q2" content={multipleContent} onSubmit={onSubmit} />);

      fireEvent.click(screen.getByRole("checkbox", { name: /^2$/ }));
      fireEvent.click(screen.getByRole("checkbox", { name: /^3$/ }));
      fireEvent.click(screen.getByRole("button", { name: "Check answer" }));

      expect(onSubmit).toHaveBeenCalledWith("q2", expect.arrayContaining(["a", "b"]), true);
      const [, selectedIds, isCorrect] = onSubmit.mock.calls[0];
      expect(selectedIds).toHaveLength(2);
      expect(isCorrect).toBe(true);
    });

    it("marks answer as incorrect when only one of two correct options selected", () => {
      const onSubmit = vi.fn();
      render(<QuizBlock blockId="q2" content={multipleContent} onSubmit={onSubmit} />);

      fireEvent.click(screen.getByRole("checkbox", { name: /^2$/ }));
      fireEvent.click(screen.getByRole("button", { name: "Check answer" }));

      expect(onSubmit).toHaveBeenCalledWith("q2", ["a"], false);
    });
  });

  describe("previewMode", () => {
    it("does not render the Check answer button in preview mode", () => {
      render(<QuizBlock blockId="q1" content={singleContent} previewMode />);
      expect(screen.queryByRole("button", { name: "Check answer" })).not.toBeInTheDocument();
    });

    it("disables all option buttons in preview mode", () => {
      render(<QuizBlock blockId="q1" content={singleContent} previewMode />);
      screen.getAllByRole("radio").forEach((r) => expect(r).toBeDisabled());
    });

    it("does not allow selection in preview mode", () => {
      render(<QuizBlock blockId="q1" content={singleContent} previewMode />);
      const radio = screen.getByRole("radio", { name: /4/ });
      fireEvent.click(radio);
      expect(radio).toHaveAttribute("aria-checked", "false");
    });
  });

  describe("onSubmit not provided", () => {
    it("does not throw when onSubmit is not provided", () => {
      render(<QuizBlock blockId="q1" content={singleContent} />);
      fireEvent.click(screen.getByRole("radio", { name: /4/ }));
      expect(() =>
        fireEvent.click(screen.getByRole("button", { name: "Check answer" }))
      ).not.toThrow();
    });
  });
});
