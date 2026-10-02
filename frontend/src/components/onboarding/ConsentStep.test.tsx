import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ConsentStep } from "./ConsentStep";

describe("ConsentStep", () => {
  let onAgree: Mock<() => void>;
  let onBack: Mock<() => void>;

  beforeEach(() => {
    onAgree = vi.fn();
    onBack = vi.fn();
  });

  // Helper to get fresh props referencing current mocks
  function makeProps(overrides: Partial<Parameters<typeof ConsentStep>[0]> = {}) {
    return {
      onAgree,
      onBack,
      isSubmitting: false,
      currentStep: 2,
      totalSteps: 3,
      ...overrides,
    };
  }

  describe("rendering", () => {
    it("renders the heading", () => {
      render(<ConsentStep {...makeProps()} />);
      expect(screen.getByRole("heading", { name: "Research Study Consent" })).toBeInTheDocument();
    });

    it("renders the subtext", () => {
      render(<ConsentStep {...makeProps()} />);
      expect(
        screen.getByText("Please read the following carefully before participating.")
      ).toBeInTheDocument();
    });

    it("renders the consent checkbox", () => {
      render(<ConsentStep {...makeProps()} />);
      expect(screen.getByRole("checkbox")).toBeInTheDocument();
    });

    it("renders the checkbox label text", () => {
      render(<ConsentStep {...makeProps()} />);
      expect(
        screen.getByText("I have read and understood the above consent information")
      ).toBeInTheDocument();
    });

    it("checkbox is unchecked initially", () => {
      render(<ConsentStep {...makeProps()} />);
      expect(screen.getByRole("checkbox")).not.toBeChecked();
    });

    it("renders 'I agree' button", () => {
      render(<ConsentStep {...makeProps()} />);
      expect(screen.getByRole("button", { name: "I agree" })).toBeInTheDocument();
    });

    it("renders 'Back' button", () => {
      render(<ConsentStep {...makeProps()} />);
      expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    });

    it("renders the step indicator", () => {
      render(<ConsentStep {...makeProps()} />);
      expect(screen.getByLabelText("Step 2 of 3")).toBeInTheDocument();
    });
  });

  describe("'I agree' button disabled state", () => {
    it("'I agree' button is disabled when checkbox is unchecked", () => {
      render(<ConsentStep {...makeProps()} />);
      expect(screen.getByRole("button", { name: "I agree" })).toBeDisabled();
    });

    it("'I agree' button has aria-disabled=true when checkbox is unchecked", () => {
      render(<ConsentStep {...makeProps()} />);
      expect(screen.getByRole("button", { name: "I agree" })).toHaveAttribute("aria-disabled", "true");
    });

    it("'I agree' button is enabled after checkbox is checked", () => {
      render(<ConsentStep {...makeProps()} />);
      fireEvent.click(screen.getByRole("checkbox"));
      expect(screen.getByRole("button", { name: "I agree" })).not.toBeDisabled();
    });

    it("'I agree' button has aria-disabled=false after checkbox is checked", () => {
      render(<ConsentStep {...makeProps()} />);
      fireEvent.click(screen.getByRole("checkbox"));
      expect(screen.getByRole("button", { name: "I agree" })).toHaveAttribute("aria-disabled", "false");
    });

    it("'I agree' button is disabled when isSubmitting=true (checkbox unchecked)", () => {
      render(<ConsentStep {...makeProps({ isSubmitting: true })} />);
      expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    });

    it("'I agree' button is disabled when isSubmitting=true even when checkbox would be checked", () => {
      // isSubmitting=true means !checked || isSubmitting → true → disabled
      // Check that the button is disabled via aria-disabled
      render(<ConsentStep {...makeProps({ isSubmitting: true })} />);
      expect(screen.getByRole("button", { name: "Saving…" })).toHaveAttribute("aria-disabled", "true");
    });

    it("button label changes to 'Saving…' when isSubmitting=true", () => {
      render(<ConsentStep {...makeProps({ isSubmitting: true })} />);
      expect(screen.getByText("Saving…")).toBeInTheDocument();
    });
  });

  describe("checkbox interaction", () => {
    it("toggles checked state when clicked", () => {
      render(<ConsentStep {...makeProps()} />);
      const checkbox = screen.getByRole("checkbox");

      fireEvent.click(checkbox);
      expect(checkbox).toBeChecked();

      fireEvent.click(checkbox);
      expect(checkbox).not.toBeChecked();
    });

    it("checking then unchecking re-disables the 'I agree' button", () => {
      render(<ConsentStep {...makeProps()} />);
      const checkbox = screen.getByRole("checkbox");

      fireEvent.click(checkbox);
      expect(screen.getByRole("button", { name: "I agree" })).not.toBeDisabled();

      fireEvent.click(checkbox);
      expect(screen.getByRole("button", { name: "I agree" })).toBeDisabled();
    });
  });

  describe("'I agree' button click", () => {
    it("calls onAgree when checkbox is checked and button clicked", () => {
      render(<ConsentStep {...makeProps()} />);
      fireEvent.click(screen.getByRole("checkbox"));
      fireEvent.click(screen.getByRole("button", { name: "I agree" }));
      expect(onAgree).toHaveBeenCalledTimes(1);
    });

    it("does not call onAgree when button is disabled (checkbox unchecked)", () => {
      render(<ConsentStep {...makeProps()} />);
      fireEvent.click(screen.getByRole("button", { name: "I agree" }));
      expect(onAgree).not.toHaveBeenCalled();
    });
  });

  describe("'Back' button", () => {
    it("calls onBack when Back button is clicked", () => {
      render(<ConsentStep {...makeProps()} />);
      fireEvent.click(screen.getByRole("button", { name: "Back" }));
      expect(onBack).toHaveBeenCalledTimes(1);
    });

    it("Back button is not disabled", () => {
      render(<ConsentStep {...makeProps()} />);
      expect(screen.getByRole("button", { name: "Back" })).not.toBeDisabled();
    });

    it("Back button can be clicked regardless of checkbox state", () => {
      render(<ConsentStep {...makeProps()} />);
      fireEvent.click(screen.getByRole("button", { name: "Back" }));
      expect(onBack).toHaveBeenCalled();
    });

    it("calls onBack even when isSubmitting is true", () => {
      render(<ConsentStep {...makeProps({ isSubmitting: true })} />);
      fireEvent.click(screen.getByRole("button", { name: "Back" }));
      expect(onBack).toHaveBeenCalledTimes(1);
    });
  });

  describe("consent sections", () => {
    it("renders webcam consent section heading", () => {
      render(<ConsentStep {...makeProps()} />);
      expect(screen.getByText("Webcam Facial Analysis")).toBeInTheDocument();
    });

    it("renders behavioural tracking section heading", () => {
      render(<ConsentStep {...makeProps()} />);
      expect(screen.getByText("Mouse & Keyboard Behavioural Tracking")).toBeInTheDocument();
    });

    it("renders data usage section heading", () => {
      render(<ConsentStep {...makeProps()} />);
      expect(screen.getByText("Data Usage & Storage")).toBeInTheDocument();
    });

    it("renders right to withdraw section heading", () => {
      render(<ConsentStep {...makeProps()} />);
      expect(screen.getByText("Right to Withdraw")).toBeInTheDocument();
    });
  });

  describe("isSubmitting state", () => {
    it("renders 'Saving…' text when isSubmitting=true", () => {
      render(<ConsentStep {...makeProps({ isSubmitting: true })} />);
      expect(screen.getByText("Saving…")).toBeInTheDocument();
    });

    it("agree button has aria-disabled=true when isSubmitting with rerender", () => {
      const { rerender } = render(<ConsentStep {...makeProps()} />);
      rerender(<ConsentStep {...makeProps({ isSubmitting: true })} />);
      expect(screen.getByRole("button", { name: "Saving…" })).toHaveAttribute("aria-disabled", "true");
    });
  });
});
