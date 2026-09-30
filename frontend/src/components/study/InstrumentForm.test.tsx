import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { InstrumentForm } from "./InstrumentForm";
import { LESSON_FEEDBACK, SUS, UEQ_S, isComplete, visibleAnswers } from "./instruments";

function choose(groupName: string, value: string) {
  const input = document.querySelector(
    `input[name="${groupName}"][value="${value}"]`,
  ) as HTMLInputElement;
  fireEvent.click(input);
}

describe("instrument definitions", () => {
  it("reproduces the validated scales at their published length", () => {
    expect(SUS.items).toHaveLength(10);
    expect(UEQ_S.items).toHaveLength(8);
    expect(SUS.items[0]).toMatchObject({
      prompt: "I think that I would like to use this system frequently.",
    });
    expect(UEQ_S.items[0]).toMatchObject({ left: "obstructive", right: "supportive" });
  });

  it("only asks the follow-ups when a change was noticed, and never sends them hidden", () => {
    const base = { difficulty: "3", easy_to_understand: "4", responded_to_needs: "3" };
    expect(isComplete(LESSON_FEEDBACK, { ...base, noticed_change: "no" })).toBe(true);
    expect(
      visibleAnswers(LESSON_FEEDBACK, { ...base, noticed_change: "no", change_helpful: "5" }),
    ).not.toHaveProperty("change_helpful");
    expect(
      visibleAnswers(LESSON_FEEDBACK, { ...base, noticed_change: "yes", change_helpful: "5" }),
    ).toHaveProperty("change_helpful", "5");
  });
});

describe("InstrumentForm", () => {
  it("keeps submit disabled until every shown required item is answered", () => {
    const onSubmit = vi.fn();
    render(<InstrumentForm def={LESSON_FEEDBACK} onSubmit={onSubmit} compact />);
    const submit = screen.getByRole("button", { name: "Continue" });
    expect(submit).toBeDisabled();
    choose("lesson_feedback-difficulty", "4");
    choose("lesson_feedback-easy_to_understand", "3");
    choose("lesson_feedback-noticed_change", "no");
    expect(submit).toBeDisabled();
    choose("lesson_feedback-responded_to_needs", "3");
    expect(submit).not.toBeDisabled();
    fireEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      skipped: false,
      responses: { difficulty: "4", easy_to_understand: "3", noticed_change: "no",
                   responded_to_needs: "3" },
    }));
  });

  it("shows the follow-ups once a change is noticed", () => {
    render(<InstrumentForm def={LESSON_FEEDBACK} onSubmit={vi.fn()} compact />);
    expect(screen.queryByText("The changes were helpful.")).toBeNull();
    choose("lesson_feedback-noticed_change", "yes");
    expect(screen.getByText("The changes were helpful.")).toBeInTheDocument();
  });

  it("records a skip with no answers", () => {
    const onSubmit = vi.fn();
    render(<InstrumentForm def={LESSON_FEEDBACK} onSubmit={onSubmit} allowSkip compact />);
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ skipped: true, responses: {} }));
  });

  it("renders the UEQ-S as seven-point differentials", () => {
    render(<InstrumentForm def={UEQ_S} onSubmit={vi.fn()} />);
    expect(document.querySelectorAll('input[name="ueq_s-q1"]')).toHaveLength(7);
    expect(screen.getByText("obstructive")).toBeInTheDocument();
    expect(screen.getByText("supportive")).toBeInTheDocument();
  });
});
