import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, within, waitFor, cleanup } from "@testing-library/react";

import { QuestionnaireStep, type QuestionnaireValues } from "./QuestionnaireStep";
import { TOTAL_SECTIONS } from "./questionnaire-questions";

describe("QuestionnaireStep", () => {
  let onSubmit: ReturnType<typeof vi.fn<(responses: QuestionnaireValues) => Promise<void>>>;

  beforeEach(() => {
    onSubmit = vi.fn<(responses: QuestionnaireValues) => Promise<void>>().mockResolvedValue(undefined);
  });

  // The shared test-setup does not register global auto-cleanup, so unmount the
  // previous render between tests — otherwise accumulated DOM yields duplicate
  // questionnaire sections and "multiple elements" query failures.
  afterEach(() => {
    cleanup();
  });

  function makeProps(
    overrides: Partial<Parameters<typeof QuestionnaireStep>[0]> = {},
  ): Parameters<typeof QuestionnaireStep>[0] {
    return {
      onSubmit,
      isSubmitting: false,
      currentStep: 5,
      totalSteps: 5,
      ...overrides,
    };
  }

  // --- helpers operating on the live DOM (one section visible at a time) ---
  function selectRadio(groupName: string | RegExp, optionLabel: string | RegExp) {
    const name = typeof groupName === "string" ? new RegExp(groupName, "i") : groupName;
    const group = screen.getByRole("radiogroup", { name });
    fireEvent.click(within(group).getByRole("radio", { name: optionLabel }));
  }

  function answerVisibleSection() {
    // First section: Demographics (Q1 age, Q2 gender)
    if (screen.queryByText("About you")) {
      selectRadio("Age", "21-23");
      selectRadio("Gender", "Female");
    } else if (screen.queryByText("Your online learning background")) {
      selectRadio("How frequently do you use online learning", "Once a week");
      selectRadio("how many online courses have you started", "3-5");
      selectRadio("how many have you fully completed", "1-2");
    } else if (screen.queryByText("Technology & preferences")) {
      selectRadio("comfortable are you with your webcam", "Comfortable");
      selectRadio("most preferred content format", "Video explanations");
    } else if (screen.queryByText("Your experiences while learning")) {
      // Q8 matrix — each row is its own radiogroup (anchor to the row label so the
      // matcher doesn't also hit Q10, whose prompt lists "boredom, confusion, frustration")
      selectRadio(/^Boredom/i, "Sometimes");
      selectRadio(/^Confusion/i, "Often");
      selectRadio(/^Frustration/i, "Rarely");
      selectRadio(/^Engagement/i, "Very Often");
      // Q9 multi-select is optional; leave it (tested separately)
      selectRadio("abandoned or dropped an online course", "No, never");
      selectRadio("If the online course had adapted", "Agree");
    } else if (screen.queryByText("Your confidence in online learning")) {
      selectRadio("I am confident in my ability", "Agree");
      selectRadio("I can stay focused", "Neutral");
      selectRadio("without external motivation", "Strongly Agree");
    }
  }

  describe("rendering & progressive disclosure", () => {
    it("renders the personalization framing (not 'research data collection')", () => {
      render(<QuestionnaireStep {...makeProps()} />);
      expect(
        screen.getByRole("heading", { name: "Help us personalize your experience" }),
      ).toBeInTheDocument();
      expect(screen.queryByText(/research data collection/i)).not.toBeInTheDocument();
    });

    it("shows the progress indicator with 'Section 1 of N'", () => {
      render(<QuestionnaireStep {...makeProps()} />);
      expect(
        screen.getByText(new RegExp(`Section 1 of ${TOTAL_SECTIONS}`)),
      ).toBeInTheDocument();
    });

    it("shows only the first section's questions initially (one section at a time)", () => {
      render(<QuestionnaireStep {...makeProps()} />);
      // Q1 (Age) visible, a later-section question (Q7 content format) not visible
      expect(screen.getByRole("radiogroup", { name: /Age/i })).toBeInTheDocument();
      expect(
        screen.queryByRole("radiogroup", { name: /most preferred content format/i }),
      ).not.toBeInTheDocument();
    });

    it("renders the step indicator", () => {
      render(<QuestionnaireStep {...makeProps()} />);
      expect(screen.getByLabelText("Step 5 of 5")).toBeInTheDocument();
    });
  });

  describe("Next gating", () => {
    it("Next is disabled until the section's required questions are answered", () => {
      render(<QuestionnaireStep {...makeProps()} />);
      expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
      selectRadio("Age", "21-23");
      expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
      selectRadio("Gender", "Female");
      expect(screen.getByRole("button", { name: "Next" })).not.toBeDisabled();
    });

    it("Back is disabled on the first section", () => {
      render(<QuestionnaireStep {...makeProps()} />);
      expect(screen.getByRole("button", { name: "Back" })).toBeDisabled();
    });

    it("advances to the next section on Next and can go Back", () => {
      render(<QuestionnaireStep {...makeProps()} />);
      answerVisibleSection();
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
      expect(screen.getByText(/Section 2 of/)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Back" }));
      expect(screen.getByText(/Section 1 of/)).toBeInTheDocument();
      // Previously selected answer is retained
      const ageGroup = screen.getByRole("radiogroup", { name: /Age/i });
      expect(within(ageGroup).getByRole("radio", { name: "21-23" })).toBeChecked();
    });
  });

  describe("multi-select (Q9)", () => {
    it("Q9 is optional — section is completable without selecting any option", () => {
      render(<QuestionnaireStep {...makeProps()} />);
      // navigate to the affect section (index 3)
      for (let i = 0; i < 3; i++) {
        answerVisibleSection();
        fireEvent.click(screen.getByRole("button", { name: "Next" }));
      }
      // Answer all required affect questions but NOT Q9
      answerVisibleSection();
      expect(screen.getByRole("button", { name: "Next" })).not.toBeDisabled();
    });

    it("toggles multiple Q9 checkboxes on and off", () => {
      render(<QuestionnaireStep {...makeProps()} />);
      for (let i = 0; i < 3; i++) {
        answerVisibleSection();
        fireEvent.click(screen.getByRole("button", { name: "Next" }));
      }
      const group = screen.getByRole("group", { name: /When you feel disengaged/i });
      const takeBreak = within(group).getByRole("checkbox", { name: "Take a break and return later" });
      fireEvent.click(takeBreak);
      expect(takeBreak).toBeChecked();
      fireEvent.click(takeBreak);
      expect(takeBreak).not.toBeChecked();
    });
  });

  describe("Likert matrix (Q8)", () => {
    it("renders one labeled radiogroup per affect row", () => {
      render(<QuestionnaireStep {...makeProps()} />);
      for (let i = 0; i < 3; i++) {
        answerVisibleSection();
        fireEvent.click(screen.getByRole("button", { name: "Next" }));
      }
      expect(screen.getByRole("radiogroup", { name: /^Boredom/i })).toBeInTheDocument();
      expect(screen.getByRole("radiogroup", { name: /^Confusion/i })).toBeInTheDocument();
      expect(screen.getByRole("radiogroup", { name: /^Frustration/i })).toBeInTheDocument();
      expect(screen.getByRole("radiogroup", { name: /^Engagement/i })).toBeInTheDocument();
    });

    it("selecting a rating in one row does not affect another row", () => {
      render(<QuestionnaireStep {...makeProps()} />);
      for (let i = 0; i < 3; i++) {
        answerVisibleSection();
        fireEvent.click(screen.getByRole("button", { name: "Next" }));
      }
      const boredom = screen.getByRole("radiogroup", { name: /^Boredom/i });
      const confusion = screen.getByRole("radiogroup", { name: /^Confusion/i });
      fireEvent.click(within(boredom).getByRole("radio", { name: "Often" }));
      expect(within(boredom).getByRole("radio", { name: "Often" })).toBeChecked();
      expect(within(confusion).getByRole("radio", { name: "Often" })).not.toBeChecked();
    });
  });

  describe("submit", () => {
    it("shows Finish on the last section and calls onSubmit with the collected answers", async () => {
      render(<QuestionnaireStep {...makeProps()} />);
      // Walk every section, answering required questions.
      for (let i = 0; i < TOTAL_SECTIONS; i++) {
        answerVisibleSection();
        if (i < TOTAL_SECTIONS - 1) {
          fireEvent.click(screen.getByRole("button", { name: "Next" }));
        }
      }
      const finish = screen.getByRole("button", { name: "Finish" });
      expect(finish).not.toBeDisabled();
      fireEvent.click(finish);

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
      const payload = onSubmit.mock.calls[0][0];
      expect(payload.Q1).toBe("21-23");
      expect(payload.Q2).toBe("female");
      expect(payload.Q8).toEqual({
        boredom: "3",
        confusion: "4",
        frustration: "2",
        engagement: "5",
      });
      expect(payload.Q14).toBe("5");
      expect(Array.isArray(payload.Q9)).toBe(true);
    });

    it("disables Finish while isSubmitting", async () => {
      render(<QuestionnaireStep {...makeProps({ isSubmitting: true })} />);
      for (let i = 0; i < TOTAL_SECTIONS; i++) {
        answerVisibleSection();
        if (i < TOTAL_SECTIONS - 1) {
          fireEvent.click(screen.getByRole("button", { name: "Next" }));
        }
      }
      expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    });
  });
});
