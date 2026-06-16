import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SkipAheadCard } from "./SkipAheadCard";
import type { Adaptation } from "@/stores/adaptation-store";

function makeSkip(text?: string): Adaptation {
  return { id: "id-skip_ahead", action: "skip_ahead", text, receivedAt: Date.now() };
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

const COPY = "Looks like you've got this — skip to the challenge exercise?";

describe("SkipAheadCard", () => {
  beforeEach(() => {
    // Default: reduced motion ON so accept/dismiss resolve synchronously.
    stubMatchMedia(true);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("render + a11y", () => {
    it("renders the spec'd copy and both accept + dismiss controls", () => {
      render(<SkipAheadCard adaptation={makeSkip()} onAccept={vi.fn()} onDismiss={vi.fn()} />);
      expect(screen.getByText(COPY)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Skip ahead" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Not now" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Dismiss suggestion" })).toBeInTheDocument();
    });

    it("exposes role=complementary, aria-label and is focusable", () => {
      render(<SkipAheadCard adaptation={makeSkip()} onAccept={vi.fn()} onDismiss={vi.fn()} />);
      const region = screen.getByRole("complementary", { name: "Skip ahead suggestion" });
      expect(region).toBeInTheDocument();
      expect(region).toHaveAttribute("tabindex", "0");
      expect(region.className).toContain("border-l-[3px]");
      expect(region.className).toContain("border-primary");
      expect(region.className).toContain("bg-primary-soft");
    });
  });

  describe("accept", () => {
    it("calls onAccept once and hides the suggestion", async () => {
      const onAccept = vi.fn();
      const user = userEvent.setup();
      render(<SkipAheadCard adaptation={makeSkip()} onAccept={onAccept} onDismiss={vi.fn()} />);
      await user.click(screen.getByRole("button", { name: "Skip ahead" }));
      expect(onAccept).toHaveBeenCalledTimes(1);
      expect(screen.queryByText(COPY)).not.toBeInTheDocument();
    });
  });

  describe("dismiss", () => {
    it("calls onDismiss and hides when 'Not now' is clicked", async () => {
      const onDismiss = vi.fn();
      const user = userEvent.setup();
      render(<SkipAheadCard adaptation={makeSkip()} onAccept={vi.fn()} onDismiss={onDismiss} />);
      await user.click(screen.getByRole("button", { name: "Not now" }));
      expect(onDismiss).toHaveBeenCalledTimes(1);
      expect(screen.queryByText(COPY)).not.toBeInTheDocument();
    });

    it("calls onDismiss when the X dismiss button is clicked", async () => {
      const onDismiss = vi.fn();
      const user = userEvent.setup();
      render(<SkipAheadCard adaptation={makeSkip()} onAccept={vi.fn()} onDismiss={onDismiss} />);
      await user.click(screen.getByRole("button", { name: "Dismiss suggestion" }));
      expect(onDismiss).toHaveBeenCalledTimes(1);
    });

    it("dismisses on scoped Escape and does NOT propagate to window keydown listeners", async () => {
      const windowHandler = vi.fn();
      window.addEventListener("keydown", windowHandler);
      const onDismiss = vi.fn();
      const user = userEvent.setup();
      render(<SkipAheadCard adaptation={makeSkip()} onAccept={vi.fn()} onDismiss={onDismiss} />);
      const region = screen.getByRole("complementary", { name: "Skip ahead suggestion" });
      region.focus();
      await user.keyboard("{Escape}");
      expect(onDismiss).toHaveBeenCalledTimes(1);
      // nativeEvent.stopImmediatePropagation() prevents the event reaching window listeners
      // (the lesson page's focus-mode Escape handler must NOT fire).
      expect(windowHandler).not.toHaveBeenCalled();
      window.removeEventListener("keydown", windowHandler);
    });

    it("does not double-fire when accept and dismiss are both triggered rapidly", async () => {
      stubMatchMedia(false); // motion allowed → JS-timed fade-out path
      const onAccept = vi.fn();
      const onDismiss = vi.fn();
      const user = userEvent.setup();
      render(<SkipAheadCard adaptation={makeSkip()} onAccept={onAccept} onDismiss={onDismiss} />);
      const accept = screen.getByRole("button", { name: "Skip ahead" });
      await user.click(accept);
      // A second interaction after the first is ignored by the actedRef guard.
      await user.click(screen.getByRole("button", { name: "Not now" }));
      await waitFor(() => expect(screen.queryByText(COPY)).not.toBeInTheDocument());
      expect(onAccept).toHaveBeenCalledTimes(1);
      expect(onDismiss).not.toHaveBeenCalled();
    });
  });

  describe("reduced motion", () => {
    it("resolves accept synchronously under reduced motion (no JS-timed delay)", async () => {
      stubMatchMedia(true);
      const onAccept = vi.fn();
      const user = userEvent.setup();
      render(<SkipAheadCard adaptation={makeSkip()} onAccept={onAccept} onDismiss={vi.fn()} />);
      await user.click(screen.getByRole("button", { name: "Skip ahead" }));
      expect(onAccept).toHaveBeenCalledTimes(1);
      expect(screen.queryByText(COPY)).not.toBeInTheDocument();
    });

    it("uses CSS transition utility classes so the global reduced-motion rule applies", () => {
      render(<SkipAheadCard adaptation={makeSkip()} onAccept={vi.fn()} onDismiss={vi.fn()} />);
      const region = screen.getByRole("complementary", { name: "Skip ahead suggestion" });
      expect(region.className).toContain("transition-");
      expect(region.className).toContain("duration-300");
    });
  });
});
