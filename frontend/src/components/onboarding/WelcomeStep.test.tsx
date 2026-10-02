import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WelcomeStep } from "./WelcomeStep";

describe("WelcomeStep", () => {
  let onNext: Mock<() => void>;

  beforeEach(() => {
    onNext = vi.fn();
  });

  describe("heading text", () => {
    it("shows personalised heading when firstName is provided", () => {
      render(
        <WelcomeStep
          firstName="Lakshitha"
          onNext={onNext}
          currentStep={1}
          totalSteps={3}
        />
      );
      expect(
        screen.getByText("Welcome, Lakshitha! Let's set up your learning experience.")
      ).toBeInTheDocument();
    });

    it("shows generic heading when firstName is null", () => {
      render(
        <WelcomeStep
          firstName={null}
          onNext={onNext}
          currentStep={1}
          totalSteps={3}
        />
      );
      expect(
        screen.getByText("Welcome! Let's set up your learning experience.")
      ).toBeInTheDocument();
    });

    it("does not show personalised heading when firstName is null", () => {
      render(
        <WelcomeStep
          firstName={null}
          onNext={onNext}
          currentStep={1}
          totalSteps={3}
        />
      );
      expect(screen.queryByText(/Welcome,/)).not.toBeInTheDocument();
    });

    it("heading is rendered as an h1", () => {
      render(
        <WelcomeStep
          firstName="Lakshitha"
          onNext={onNext}
          currentStep={1}
          totalSteps={3}
        />
      );
      expect(
        screen.getByRole("heading", { level: 1 })
      ).toHaveTextContent("Welcome, Lakshitha! Let's set up your learning experience.");
    });
  });

  describe("subtext", () => {
    it("renders the descriptive paragraph", () => {
      render(
        <WelcomeStep
          firstName="Lakshitha"
          onNext={onNext}
          currentStep={1}
          totalSteps={3}
        />
      );
      expect(
        screen.getByText(/Before you start learning, we need to set up a few things/)
      ).toBeInTheDocument();
    });
  });

  describe("Get started button", () => {
    it("renders the 'Get started' button", () => {
      render(
        <WelcomeStep
          firstName={null}
          onNext={onNext}
          currentStep={1}
          totalSteps={3}
        />
      );
      expect(screen.getByRole("button", { name: "Get started" })).toBeInTheDocument();
    });

    it("calls onNext when 'Get started' button is clicked", () => {
      render(
        <WelcomeStep
          firstName={null}
          onNext={onNext}
          currentStep={1}
          totalSteps={3}
        />
      );
      fireEvent.click(screen.getByRole("button", { name: "Get started" }));
      expect(onNext).toHaveBeenCalledTimes(1);
    });

    it("calls onNext each time button is clicked", () => {
      render(
        <WelcomeStep
          firstName={null}
          onNext={onNext}
          currentStep={1}
          totalSteps={3}
        />
      );
      fireEvent.click(screen.getByRole("button", { name: "Get started" }));
      fireEvent.click(screen.getByRole("button", { name: "Get started" }));
      expect(onNext).toHaveBeenCalledTimes(2);
    });
  });

  describe("step indicator", () => {
    it("renders a step indicator with correct step info", () => {
      render(
        <WelcomeStep
          firstName={null}
          onNext={onNext}
          currentStep={1}
          totalSteps={3}
        />
      );
      expect(screen.getByLabelText("Step 1 of 3")).toBeInTheDocument();
    });

    it("passes totalSteps correctly to the step indicator", () => {
      render(
        <WelcomeStep
          firstName={null}
          onNext={onNext}
          currentStep={2}
          totalSteps={4}
        />
      );
      expect(screen.getByLabelText("Step 2 of 4")).toBeInTheDocument();
    });
  });

  describe("different firstNames", () => {
    it("shows the correct firstName in heading", () => {
      render(
        <WelcomeStep
          firstName="Alice"
          onNext={onNext}
          currentStep={1}
          totalSteps={2}
        />
      );
      expect(screen.getByText("Welcome, Alice! Let's set up your learning experience.")).toBeInTheDocument();
    });

    it("handles firstName with spaces", () => {
      render(
        <WelcomeStep
          firstName="Mary Jane"
          onNext={onNext}
          currentStep={1}
          totalSteps={2}
        />
      );
      expect(
        screen.getByText("Welcome, Mary Jane! Let's set up your learning experience.")
      ).toBeInTheDocument();
    });
  });
});
