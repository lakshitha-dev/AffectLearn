import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { renderHook } from "@testing-library/react";

import { QuizBlock } from "@/components/learning/QuizBlock";
import { ExerciseBlock } from "@/components/learning/ExerciseBlock";
import { QUIZ_ACTIVITY_THROTTLE_MS, useQuizActivity } from "./use-quiz-activity";

const quiz = {
  question: "What is 2 + 2?",
  type: "single" as const,
  options: [
    { id: "a", text: "3", isCorrect: false },
    { id: "b", text: "4", isCorrect: true },
  ],
  explanation: "2 + 2 equals 4.",
};

const exercise = { prompt: "Type the keyword that defines a function", answer: "def" };

function quizActivityReports(send: ReturnType<typeof vi.fn>) {
  return send.mock.calls.filter((c) => c[0]?.data?.event === "quiz_activity");
}

describe("useQuizActivity", () => {
  let now = 1_000_000;

  beforeEach(() => {
    now = 1_000_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("reports answering a lesson quiz, so the server's quiz_active hold can fire", () => {
    const send = vi.fn();
    renderHook(() => useQuizActivity(send));
    render(<QuizBlock blockId="q1" content={quiz} />);

    fireEvent.pointerDown(screen.getByText("4"));

    expect(quizActivityReports(send)).toHaveLength(1);
    expect(send.mock.calls[0][0]).toEqual({
      type: "ui_event",
      ts: now,
      data: { event: "quiz_activity" },
    });
  });

  it("reports typing into a lesson exercise", () => {
    const send = vi.fn();
    renderHook(() => useQuizActivity(send));
    render(<ExerciseBlock blockId="e1" content={exercise} />);

    fireEvent.keyDown(screen.getByPlaceholderText("Your answer…"), { key: "d" });

    expect(quizActivityReports(send)).toHaveLength(1);
  });

  it("ignores interaction outside a quiz or exercise", () => {
    const send = vi.fn();
    renderHook(() => useQuizActivity(send));
    render(<p>Plain lesson text</p>);

    fireEvent.pointerDown(screen.getByText("Plain lesson text"));

    expect(quizActivityReports(send)).toHaveLength(0);
  });

  it("throttles repeated activity to one report per window", () => {
    const send = vi.fn();
    renderHook(() => useQuizActivity(send));
    render(<QuizBlock blockId="q1" content={quiz} />);

    fireEvent.pointerDown(screen.getByText("3"));
    now += QUIZ_ACTIVITY_THROTTLE_MS - 1;
    fireEvent.pointerDown(screen.getByText("4"));
    expect(quizActivityReports(send)).toHaveLength(1);

    now += 1;
    fireEvent.pointerDown(screen.getByText("4"));
    expect(quizActivityReports(send)).toHaveLength(2);
  });

  it("marks both lesson blocks as quiz regions", () => {
    const { container: q } = render(<QuizBlock blockId="q1" content={quiz} />);
    const { container: e } = render(<ExerciseBlock blockId="e1" content={exercise} />);
    expect(q.querySelector("[data-quiz]")).not.toBeNull();
    expect(e.querySelector("[data-quiz]")).not.toBeNull();
  });
});
