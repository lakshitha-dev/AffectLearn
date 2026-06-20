import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SelfReportBar } from "./SelfReportBar";

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

const QUESTION = "Quick check: How are you feeling about this material?";
const LABELS = ["Engaged", "Confused", "Bored", "Frustrated", "Neutral"];

describe("SelfReportBar", () => {
  beforeEach(() => {
    stubMatchMedia(false);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("render + a11y (AC1, AC6)", () => {
    it("renders the exact question copy, all 5 labeled options in order, and Skip", () => {
      render(<SelfReportBar onReport={vi.fn()} />);
      expect(screen.getByText(QUESTION)).toBeInTheDocument();
      const radios = screen.getAllByRole("radio");
      expect(radios.map((r) => r.textContent)).toEqual(LABELS);
      expect(screen.getByRole("button", { name: "Skip" })).toBeInTheDocument();
    });

    it("wraps the options in a radiogroup with aria-label 'How are you feeling?'", () => {
      render(<SelfReportBar onReport={vi.fn()} />);
      const group = screen.getByRole("radiogroup", { name: "How are you feeling?" });
      expect(group).toBeInTheDocument();
      const radios = screen.getAllByRole("radio");
      expect(radios).toHaveLength(5);
      radios.forEach((r) => expect(r).toHaveAttribute("aria-checked", "false"));
    });

    it("uses a roving tabindex (one tab stop: first radio tabindex 0, rest -1)", () => {
      render(<SelfReportBar onReport={vi.fn()} />);
      const radios = screen.getAllByRole("radio");
      expect(radios[0]).toHaveAttribute("tabindex", "0");
      radios.slice(1).forEach((r) => expect(r).toHaveAttribute("tabindex", "-1"));
    });

    it("uses design-token classes + CSS transition (reduced-motion handled globally)", () => {
      render(<SelfReportBar onReport={vi.fn()} />);
      const bar = screen.getByRole("group", { name: "Self-report check-in" });
      expect(bar.className).toContain("bg-surface");
      expect(bar.className).toContain("border-border");
      expect(bar.className).toContain("transition-opacity");
    });
  });

  describe("keyboard navigation (AC6)", () => {
    it("moves selection with arrow keys and selects the focused option with Enter", async () => {
      const onReport = vi.fn();
      const user = userEvent.setup();
      render(<SelfReportBar onReport={onReport} />);
      const radios = screen.getAllByRole("radio");
      radios[0].focus();
      // ArrowRight twice → index 2 (Bored), then Enter selects it.
      await user.keyboard("{ArrowRight}{ArrowRight}{Enter}");
      expect(onReport).toHaveBeenCalledTimes(1);
      expect(onReport).toHaveBeenCalledWith({ affect: "bored", skipped: false });
    });

    it("wraps with ArrowLeft from the first option to the last", async () => {
      const onReport = vi.fn();
      const user = userEvent.setup();
      render(<SelfReportBar onReport={onReport} />);
      screen.getAllByRole("radio")[0].focus();
      await user.keyboard("{ArrowLeft}{Enter}"); // wrap to Neutral (last)
      expect(onReport).toHaveBeenCalledWith({ affect: "neutral", skipped: false });
    });
  });

  describe("selection (AC2, AC3)", () => {
    it("highlights the chosen option, dims the others, and fires onReport once", async () => {
      const onReport = vi.fn();
      const user = userEvent.setup();
      render(<SelfReportBar onReport={onReport} />);
      await user.click(screen.getByRole("radio", { name: "Confused" }));

      expect(onReport).toHaveBeenCalledTimes(1);
      expect(onReport).toHaveBeenCalledWith({ affect: "confused", skipped: false });

      const chosen = screen.getByRole("radio", { name: "Confused" });
      expect(chosen).toHaveAttribute("aria-checked", "true");
      expect(chosen.className).toContain("bg-primary");

      const other = screen.getByRole("radio", { name: "Engaged" });
      expect(other.className).toContain("opacity-50");
      // The Skip link is gone once a selection has been made.
      expect(screen.queryByRole("button", { name: "Skip" })).not.toBeInTheDocument();
    });

    it("collapses after 1s, begins Thanks fade-out after 2s, and fully removes after 300ms (fake timers)", () => {
      // NOTE: under fake timers we drive interactions with fireEvent (not userEvent),
      // matching BreakSuggestionCard.test.tsx — userEvent's internal delays deadlock fake timers.
      vi.useFakeTimers();
      const onReport = vi.fn();
      render(<SelfReportBar onReport={onReport} />);

      fireEvent.click(screen.getByRole("radio", { name: "Engaged" }));
      // Still showing the bar before 1s.
      expect(screen.getByText(QUESTION)).toBeInTheDocument();

      // After 1s the bar collapses and "Thanks" appears (fully visible, not yet fading).
      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(screen.queryByText(QUESTION)).not.toBeInTheDocument();
      const thanks = screen.getByText("Thanks");
      expect(thanks).toBeInTheDocument();
      expect(thanks.className).toContain("opacity-100");

      // After a further 2s the CSS fade-out begins (opacity-0 applied, element still in DOM).
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      expect(screen.getByText("Thanks")).toBeInTheDocument();
      expect(screen.getByText("Thanks").className).toContain("opacity-0");

      // After a further 300ms the element is removed entirely.
      act(() => {
        vi.advanceTimersByTime(300);
      });
      expect(screen.queryByText("Thanks")).not.toBeInTheDocument();
    });

    it("ignores a rapid second selection (onReport fires once)", async () => {
      const onReport = vi.fn();
      const user = userEvent.setup();
      render(<SelfReportBar onReport={onReport} />);
      await user.click(screen.getByRole("radio", { name: "Engaged" }));
      // Buttons are disabled after the first selection; clicking again is a no-op.
      await user.click(screen.getByRole("radio", { name: "Bored" }));
      expect(onReport).toHaveBeenCalledTimes(1);
    });
  });

  describe("skip (AC4)", () => {
    it("fires onReport with {affect:null, skipped:true} and collapses with no guilt copy", async () => {
      const onReport = vi.fn();
      const user = userEvent.setup();
      render(<SelfReportBar onReport={onReport} />);
      await user.click(screen.getByRole("button", { name: "Skip" }));
      expect(onReport).toHaveBeenCalledTimes(1);
      expect(onReport).toHaveBeenCalledWith({ affect: null, skipped: true });
      expect(screen.queryByText(QUESTION)).not.toBeInTheDocument();
      // No "Are you sure?" / nag.
      expect(screen.queryByText(/sure/i)).not.toBeInTheDocument();
    });

    it("scoped Escape skips and does NOT propagate to window keydown listeners", async () => {
      const windowHandler = vi.fn();
      window.addEventListener("keydown", windowHandler);
      const onReport = vi.fn();
      const user = userEvent.setup();
      render(<SelfReportBar onReport={onReport} />);
      const bar = screen.getByRole("group", { name: "Self-report check-in" });
      bar.focus();
      await user.keyboard("{Escape}");
      expect(onReport).toHaveBeenCalledWith({ affect: null, skipped: true });
      // stopImmediatePropagation prevents the lesson page's focus-mode Escape handler firing.
      expect(windowHandler).not.toHaveBeenCalled();
      window.removeEventListener("keydown", windowHandler);
    });
  });

  describe("reduced motion + cleanup (AC2)", () => {
    it("still honors the 1s/2s/300ms timing semantics under reduced motion", () => {
      stubMatchMedia(true);
      vi.useFakeTimers();
      render(<SelfReportBar onReport={vi.fn()} />);
      fireEvent.click(screen.getByRole("radio", { name: "Neutral" }));
      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(screen.getByText("Thanks")).toBeInTheDocument();
      // After 2s the fade-out starts (opacity-0 applied, element still present).
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      expect(screen.getByText("Thanks")).toBeInTheDocument();
      // After a further 300ms the element is removed.
      act(() => {
        vi.advanceTimersByTime(300);
      });
      expect(screen.queryByText("Thanks")).not.toBeInTheDocument();
    });

    it("clears timers on unmount (no state-update-after-unmount)", () => {
      vi.useFakeTimers();
      const { unmount } = render(<SelfReportBar onReport={vi.fn()} />);
      fireEvent.click(screen.getByRole("radio", { name: "Engaged" }));
      unmount();
      // Advancing past both timers must not throw / warn after unmount.
      expect(() =>
        act(() => {
          vi.advanceTimersByTime(5000);
        }),
      ).not.toThrow();
    });
  });
});
