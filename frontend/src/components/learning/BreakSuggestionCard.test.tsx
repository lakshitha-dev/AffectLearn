import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { BreakSuggestionCard } from "./BreakSuggestionCard";
import type { Adaptation } from "@/stores/adaptation-store";

function makeBreak(text?: string): Adaptation {
  return { id: "id-suggest_break", action: "suggest_break", text, receivedAt: Date.now() };
}

/** Stub jsdom's missing window.matchMedia. */
function stubMatchMedia(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

const SUGGESTION_MSG = "You've been working hard. A short break can help things click.";
const TIMER_MSG = "Take your time. We'll pick up right where you left off.";
const WELCOME_MSG = "Welcome back! Ready to continue?";

describe("BreakSuggestionCard", () => {
  beforeEach(() => {
    // Default: reduced motion ON so dismiss is synchronous in most tests.
    stubMatchMedia(true);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("suggestion state", () => {
    it("renders the caring message and both buttons with role/label", () => {
      render(<BreakSuggestionCard adaptation={makeBreak()} onDismiss={vi.fn()} />);
      const dialog = screen.getByRole("alertdialog", { name: "Break suggestion" });
      expect(dialog).toBeInTheDocument();
      // The suggestion message appears in both the sr-only aria-describedby node (always
      // in the DOM for stable ARIA reference) and the visible suggestion-state <p>.
      expect(screen.getAllByText(SUGGESTION_MSG).length).toBeGreaterThanOrEqual(1);
      expect(screen.getByRole("button", { name: "Take a break" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "I'm good, continue" })).toBeInTheDocument();
    });

    it("renders a translucent overlay backdrop (not opaque, not scroll-locked)", () => {
      render(<BreakSuggestionCard adaptation={makeBreak()} onDismiss={vi.fn()} />);
      const dialog = screen.getByRole("alertdialog", { name: "Break suggestion" });
      // The overlay is the dialog's parent: fixed inset-0 with a translucent backdrop.
      const overlay = dialog.parentElement as HTMLElement;
      expect(overlay.className).toContain("fixed");
      expect(overlay.className).toContain("inset-0");
      expect(overlay.className).toContain("bg-background/70");
      // Body scroll is never locked by this overlay.
      expect(document.body.style.overflow).toBe("");
    });
  });

  describe("timer state + countdown (fake timers)", () => {
    // NOTE: under fake timers we drive interactions with fireEvent (not userEvent),
    // which is synchronous and does not rely on userEvent's internal async delays.
    it("transitions to the timer state with the countdown, message and early-return control", () => {
      vi.useFakeTimers();
      render(<BreakSuggestionCard adaptation={makeBreak()} onDismiss={vi.fn()} breakSeconds={5} />);
      fireEvent.click(screen.getByRole("button", { name: "Take a break" }));
      expect(screen.getByText(TIMER_MSG)).toBeInTheDocument();
      expect(screen.getByText("0:05")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "I'm ready, continue" })).toBeInTheDocument();
    });

    it("decrements the displayed mm:ss deterministically once per second", () => {
      vi.useFakeTimers();
      render(<BreakSuggestionCard adaptation={makeBreak()} onDismiss={vi.fn()} breakSeconds={5} />);
      fireEvent.click(screen.getByRole("button", { name: "Take a break" }));
      expect(screen.getByText("0:05")).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(screen.getByText("0:04")).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      expect(screen.getByText("0:02")).toBeInTheDocument();
    });

    it("defaults to 5:00 (300s) when no breakSeconds prop is passed", () => {
      vi.useFakeTimers();
      render(<BreakSuggestionCard adaptation={makeBreak()} onDismiss={vi.fn()} />);
      fireEvent.click(screen.getByRole("button", { name: "Take a break" }));
      expect(screen.getByText("5:00")).toBeInTheDocument();
    });

    it("transitions to welcome-back when the countdown reaches 0 (completion path)", () => {
      vi.useFakeTimers();
      render(<BreakSuggestionCard adaptation={makeBreak()} onDismiss={vi.fn()} breakSeconds={3} />);
      fireEvent.click(screen.getByRole("button", { name: "Take a break" }));
      expect(screen.getByText("0:03")).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(3000);
      });
      expect(screen.getByText(WELCOME_MSG)).toBeInTheDocument();
      expect(screen.queryByText(TIMER_MSG)).not.toBeInTheDocument();
    });
  });

  describe("early return + cleanup", () => {
    it("transitions to welcome-back when the early-return control is clicked before completion", () => {
      vi.useFakeTimers();
      render(<BreakSuggestionCard adaptation={makeBreak()} onDismiss={vi.fn()} breakSeconds={300} />);
      fireEvent.click(screen.getByRole("button", { name: "Take a break" }));
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      fireEvent.click(screen.getByRole("button", { name: "I'm ready, continue" }));
      expect(screen.getByText(WELCOME_MSG)).toBeInTheDocument();
    });

    it("clears the interval on unmount (no late state updates after unmount)", () => {
      vi.useFakeTimers();
      const { unmount } = render(
        <BreakSuggestionCard adaptation={makeBreak()} onDismiss={vi.fn()} breakSeconds={5} />,
      );
      fireEvent.click(screen.getByRole("button", { name: "Take a break" }));
      const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      unmount();
      // Advancing past the full duration must NOT trigger any further state update.
      act(() => {
        vi.advanceTimersByTime(10000);
      });
      expect(errorSpy).not.toHaveBeenCalled();
      errorSpy.mockRestore();
    });
  });

  describe("dismiss + Escape", () => {
    it("calls onDismiss when 'I'm good, continue' is clicked", async () => {
      const onDismiss = vi.fn();
      const user = userEvent.setup();
      render(<BreakSuggestionCard adaptation={makeBreak()} onDismiss={onDismiss} />);
      await user.click(screen.getByRole("button", { name: "I'm good, continue" }));
      expect(onDismiss).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    });

    it("dismisses on Escape and does NOT propagate to window-level keydown listeners", async () => {
      const windowHandler = vi.fn();
      window.addEventListener("keydown", windowHandler);
      const onDismiss = vi.fn();
      const user = userEvent.setup();
      render(<BreakSuggestionCard adaptation={makeBreak()} onDismiss={onDismiss} />);
      await user.keyboard("{Escape}");
      expect(onDismiss).toHaveBeenCalledTimes(1);
      // nativeEvent.stopImmediatePropagation() prevents the event reaching window listeners.
      expect(windowHandler).not.toHaveBeenCalled();
      window.removeEventListener("keydown", windowHandler);
    });

    it("dismisses from the timer state via Escape too", () => {
      vi.useFakeTimers();
      const onDismiss = vi.fn();
      render(<BreakSuggestionCard adaptation={makeBreak()} onDismiss={onDismiss} breakSeconds={60} />);
      fireEvent.click(screen.getByRole("button", { name: "Take a break" }));
      // reduced-motion default (stubMatchMedia(true)) → dismiss is synchronous.
      fireEvent.keyDown(screen.getByRole("alertdialog"), { key: "Escape" });
      expect(onDismiss).toHaveBeenCalledTimes(1);
    });

    it("closes the overlay when 'Continue' is clicked from welcome-back", () => {
      vi.useFakeTimers();
      const onDismiss = vi.fn();
      render(<BreakSuggestionCard adaptation={makeBreak()} onDismiss={onDismiss} breakSeconds={3} />);
      fireEvent.click(screen.getByRole("button", { name: "Take a break" }));
      act(() => {
        vi.advanceTimersByTime(3000);
      });
      fireEvent.click(screen.getByRole("button", { name: "Continue" }));
      expect(onDismiss).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    });
  });

  describe("accessibility + focus", () => {
    it("moves focus into the card (primary button) on open", async () => {
      render(<BreakSuggestionCard adaptation={makeBreak()} onDismiss={vi.fn()} />);
      const primary = screen.getByRole("button", { name: "Take a break" });
      await waitFor(() => expect(primary).toHaveFocus());
    });

    it("exposes role=alertdialog with aria-modal and aria-label", () => {
      render(<BreakSuggestionCard adaptation={makeBreak()} onDismiss={vi.fn()} />);
      const dialog = screen.getByRole("alertdialog", { name: "Break suggestion" });
      expect(dialog).toHaveAttribute("aria-modal", "true");
      expect(dialog).toHaveAttribute("aria-label", "Break suggestion");
    });
  });

  describe("reduced motion", () => {
    it("renders the breathing animation static (no animate-pulse) under reduced motion", async () => {
      stubMatchMedia(true);
      const user = userEvent.setup();
      const { container } = render(
        <BreakSuggestionCard adaptation={makeBreak()} onDismiss={vi.fn()} breakSeconds={60} />,
      );
      await user.click(screen.getByRole("button", { name: "Take a break" }));
      // useReducedMotion() resolves true → the looping pulse class is gated off.
      await waitFor(() => expect(container.querySelector(".animate-pulse")).toBeNull());
    });

    it("renders the animated breathing pulse when motion is allowed", async () => {
      stubMatchMedia(false);
      const user = userEvent.setup();
      const { container } = render(
        <BreakSuggestionCard adaptation={makeBreak()} onDismiss={vi.fn()} breakSeconds={60} />,
      );
      await user.click(screen.getByRole("button", { name: "Take a break" }));
      expect(container.querySelector(".animate-pulse")).not.toBeNull();
    });

    it("uses CSS transition utility classes so the global reduced-motion rule applies", () => {
      render(<BreakSuggestionCard adaptation={makeBreak()} onDismiss={vi.fn()} />);
      const dialog = screen.getByRole("alertdialog", { name: "Break suggestion" });
      expect(dialog.className).toContain("transition-");
      expect(dialog.className).toContain("duration-300");
    });
  });
});
