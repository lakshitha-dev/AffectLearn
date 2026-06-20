import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  within,
  waitFor,
  cleanup,
} from "@testing-library/react";

import { SatisfactionSurvey, type SurveyValues } from "./SatisfactionSurvey";
import { SATISFACTION_QUESTIONS } from "./satisfaction-questions";

describe("SatisfactionSurvey", () => {
  let onSubmit: ReturnType<typeof vi.fn<(responses: SurveyValues) => Promise<void>>>;

  beforeEach(() => {
    onSubmit = vi
      .fn<(responses: SurveyValues) => Promise<void>>()
      .mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
  });

  function selectRadio(groupName: string | RegExp, optionLabel: string | RegExp) {
    const name = typeof groupName === "string" ? new RegExp(groupName, "i") : groupName;
    const group = screen.getByRole("radiogroup", { name });
    fireEvent.click(within(group).getByRole("radio", { name: optionLabel }));
  }

  function answerAll() {
    selectRadio(/platform helped me/i, "Strongly Agree");
    selectRadio(/good learning experience/i, "Agree");
    selectRadio(/keep using AffectLearn/i, "Agree");
    selectRadio(/satisfied with AffectLearn/i, "Strongly Agree");
  }

  describe("rendering", () => {
    it("renders the 'Help us improve' framing", () => {
      render(<SatisfactionSurvey onSubmit={onSubmit} />);
      expect(
        screen.getByRole("heading", { name: /Help us improve AffectLearn/i }),
      ).toBeInTheDocument();
    });

    it("renders one labeled radiogroup per AC dimension", () => {
      render(<SatisfactionSurvey onSubmit={onSubmit} />);
      // Four dimensions → four radiogroups.
      expect(screen.getAllByRole("radiogroup")).toHaveLength(
        SATISFACTION_QUESTIONS.length,
      );
      expect(
        screen.getByRole("radiogroup", { name: /platform helped me/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("radiogroup", { name: /good learning experience/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("radiogroup", { name: /keep using AffectLearn/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("radiogroup", { name: /satisfied with AffectLearn/i }),
      ).toBeInTheDocument();
    });
  });

  describe("submit gating", () => {
    it("Submit is disabled until all required questions are answered", () => {
      render(<SatisfactionSurvey onSubmit={onSubmit} />);
      expect(screen.getByRole("button", { name: "Submit" })).toBeDisabled();
      selectRadio(/platform helped me/i, "Strongly Agree");
      expect(screen.getByRole("button", { name: "Submit" })).toBeDisabled();
      answerAll();
      expect(screen.getByRole("button", { name: "Submit" })).not.toBeDisabled();
    });

    it("disables Submit while isSubmitting", () => {
      render(<SatisfactionSurvey onSubmit={onSubmit} isSubmitting />);
      answerAll();
      expect(screen.getByRole("button", { name: "Submitting…" })).toBeDisabled();
    });
  });

  describe("submit", () => {
    it("calls onSubmit with the collected answers", async () => {
      render(<SatisfactionSurvey onSubmit={onSubmit} />);
      answerAll();
      fireEvent.click(screen.getByRole("button", { name: "Submit" }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      const payload = onSubmit.mock.calls[0][0];
      expect(payload.Q1).toBe("5");
      expect(payload.Q2).toBe("4");
      expect(payload.Q3).toBe("4");
      expect(payload.Q4).toBe("5");
    });

    it("still submits low (< 4) scores — the target is not a gate", async () => {
      render(<SatisfactionSurvey onSubmit={onSubmit} />);
      selectRadio(/platform helped me/i, "Strongly Disagree");
      selectRadio(/good learning experience/i, "Disagree");
      selectRadio(/keep using AffectLearn/i, "Strongly Disagree");
      selectRadio(/satisfied with AffectLearn/i, "Disagree");
      expect(screen.getByRole("button", { name: "Submit" })).not.toBeDisabled();
      fireEvent.click(screen.getByRole("button", { name: "Submit" }));

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      expect(onSubmit.mock.calls[0][0].Q1).toBe("1");
    });
  });
});
