import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AdaptiveHintCallout } from "./AdaptiveHintCallout";
import type { Adaptation } from "@/stores/adaptation-store";
import type { AdaptationAction } from "@/types/ws-messages";

function makeAdaptation(action: AdaptationAction, text?: string): Adaptation {
  return { id: `id-${action}`, action, text, receivedAt: Date.now() };
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

describe("AdaptiveHintCallout", () => {
  beforeEach(() => {
    // Default: reduced motion ON so dismiss is synchronous in most tests.
    stubMatchMedia(true);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("variant rendering", () => {
    it("renders the hint variant with label, body, left border and soft-bg classes", () => {
      render(
        <AdaptiveHintCallout
          adaptation={makeAdaptation("show_hint", "Try thinking of it as a recipe.")}
          onDismiss={vi.fn()}
        />,
      );
      const region = screen.getByRole("complementary", { name: "Learning hint" });
      expect(region).toBeInTheDocument();
      expect(region.className).toContain("border-l-[3px]");
      expect(region.className).toContain("border-primary");
      expect(region.className).toContain("bg-primary-soft");
      expect(screen.getByText("Here's another way to think about this…")).toBeInTheDocument();
      expect(screen.getByText("Try thinking of it as a recipe.")).toBeInTheDocument();
    });

    it("renders the breakdown variant as an expandable numbered list", () => {
      render(
        <AdaptiveHintCallout
          adaptation={makeAdaptation("show_breakdown", "First step\nSecond step\nThird step")}
          onDismiss={vi.fn()}
        />,
      );
      const list = screen.getByRole("list");
      expect(list.tagName).toBe("OL");
      const items = screen.getAllByRole("listitem");
      expect(items).toHaveLength(3);
      expect(items[0]).toHaveTextContent("First step");
      expect(items[2]).toHaveTextContent("Third step");
      // Expand/collapse control defaults expanded.
      expect(screen.getByRole("button", { name: /Let's break this down/ })).toHaveAttribute(
        "aria-expanded",
        "true",
      );
    });

    it("collapses the breakdown list when the expand control is toggled", async () => {
      const user = userEvent.setup();
      render(
        <AdaptiveHintCallout
          adaptation={makeAdaptation("show_breakdown", "Step one\nStep two")}
          onDismiss={vi.fn()}
        />,
      );
      const toggle = screen.getByRole("button", { name: /Let's break this down/ });
      await user.click(toggle);
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByRole("list")).not.toBeInTheDocument();
    });

    it("degrades breakdown gracefully to a single item when text is not splittable", () => {
      render(
        <AdaptiveHintCallout
          adaptation={makeAdaptation("show_breakdown", "A single unsplittable sentence.")}
          onDismiss={vi.fn()}
        />,
      );
      expect(screen.getAllByRole("listitem")).toHaveLength(1);
      expect(screen.getByText("A single unsplittable sentence.")).toBeInTheDocument();
    });

    it("renders the alternative variant with a distinct shade (not the hint soft-bg)", () => {
      render(
        <AdaptiveHintCallout
          adaptation={makeAdaptation("show_alternative", "Picture it as a flowchart instead.")}
          onDismiss={vi.fn()}
        />,
      );
      const region = screen.getByRole("complementary", { name: "Learning hint" });
      expect(region.className).toContain("bg-surface");
      expect(region.className).not.toContain("bg-primary-soft");
      expect(region.className).toContain("border-l-[3px]");
      expect(screen.getByText("Another way to look at this")).toBeInTheDocument();
      expect(screen.getByText("Picture it as a flowchart instead.")).toBeInTheDocument();
    });

    it("renders the encouragement variant as minimal text with no background box", () => {
      render(
        <AdaptiveHintCallout
          adaptation={makeAdaptation("show_encouragement", "You're doing great!")}
          onDismiss={vi.fn()}
        />,
      );
      const region = screen.getByRole("complementary", { name: "Learning hint" });
      expect(region.className).not.toContain("bg-primary-soft");
      expect(region.className).not.toContain("bg-surface");
      expect(region.className).not.toContain("border-l-[3px]");
      expect(screen.getByText("You're doing great!")).toBeInTheDocument();
    });

    it("uses a fallback message for encouragement when text is missing", () => {
      render(
        <AdaptiveHintCallout adaptation={makeAdaptation("show_encouragement")} onDismiss={vi.fn()} />,
      );
      expect(screen.getByText("Nice work on that section.")).toBeInTheDocument();
    });

    it("labels simplify as a simplification, not as a hint", () => {
      render(
        <AdaptiveHintCallout
          adaptation={makeAdaptation("simplify", "One step at a time: first the SYN.")}
          onDismiss={vi.fn()}
        />,
      );
      expect(screen.getByText("Put more simply")).toBeInTheDocument();
      expect(
        screen.queryByText("Here's another way to think about this…"),
      ).not.toBeInTheDocument();
    });

    it("labels increase_difficulty as a challenge, not as a hint", () => {
      // The worst case of the missing map entry. A learner is offered a HARDER question because
      // they were bored, and it arrived introduced as "Here's another way to think about this…"
      // — the framing used when someone is stuck, told to someone who is not.
      render(
        <AdaptiveHintCallout
          adaptation={makeAdaptation("increase_difficulty", "What breaks if the ACK is lost?")}
          onDismiss={vi.fn()}
        />,
      );
      expect(screen.getByText("Ready for a harder one?")).toBeInTheDocument();
      expect(
        screen.queryByText("Here's another way to think about this…"),
      ).not.toBeInTheDocument();
    });

    it("gives every action it renders a label of its own", () => {
      // Guards the class of bug rather than the two instances of it: any action routed to this
      // callout without a `VARIANT_BY_ACTION` entry silently inherits the hint label.
      const labels = new Set<string>();
      for (const action of [
        "show_hint",
        "show_alternative",
        "show_breakdown",
        "simplify",
        "increase_difficulty",
      ] as const) {
        const { unmount } = render(
          <AdaptiveHintCallout adaptation={makeAdaptation(action, "body")} onDismiss={vi.fn()} />,
        );
        const region = screen.getByRole("complementary", { name: "Learning hint" });
        // Breakdown puts its label on the expand toggle; the others put it in the leading <p>.
        // (Not `querySelector("button")` — the dismiss button is icon-only and comes first.)
        const toggle = region.querySelector("button[aria-expanded]");
        const label = (toggle ?? region.querySelector("p"))?.textContent;
        expect(label, `${action} has no label`).toBeTruthy();
        labels.add(label!);
        unmount();
      }
      expect(labels.size).toBe(5);
    });
  });

  describe("dismiss + re-access", () => {
    it("dismisses via the button, calls onDismiss, and shows the 'Show hint' affordance", async () => {
      const onDismiss = vi.fn();
      const user = userEvent.setup();
      render(
        <AdaptiveHintCallout
          adaptation={makeAdaptation("show_hint", "Hint body")}
          onDismiss={onDismiss}
        />,
      );
      await user.click(screen.getByRole("button", { name: "Dismiss hint" }));
      expect(onDismiss).toHaveBeenCalledTimes(1);
      expect(screen.queryByText("Hint body")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Show hint" })).toBeInTheDocument();
    });

    it("closes the 'Show hint' affordance for good, without reporting a second dismissal", async () => {
      const onDismiss = vi.fn();
      const onClose = vi.fn();
      const user = userEvent.setup();
      const { container } = render(
        <AdaptiveHintCallout
          adaptation={makeAdaptation("show_hint", "Hint body")}
          onDismiss={onDismiss}
          onClose={onClose}
        />,
      );
      await user.click(screen.getByRole("button", { name: "Dismiss hint" }));
      await user.click(screen.getByRole("button", { name: "Close hint" }));
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(onDismiss).toHaveBeenCalledTimes(1);
      expect(container).toBeEmptyDOMElement();
    });

    it("dismisses when Escape is pressed on the focused callout", async () => {
      const onDismiss = vi.fn();
      const user = userEvent.setup();
      render(
        <AdaptiveHintCallout
          adaptation={makeAdaptation("show_hint", "Hint body")}
          onDismiss={onDismiss}
        />,
      );
      const region = screen.getByRole("complementary", { name: "Learning hint" });
      region.focus();
      await user.keyboard("{Escape}");
      expect(onDismiss).toHaveBeenCalledTimes(1);
      expect(screen.getByRole("button", { name: "Show hint" })).toBeInTheDocument();
    });

    it("Escape on the callout does NOT propagate to window-level keydown listeners", async () => {
      const windowHandler = vi.fn();
      window.addEventListener("keydown", windowHandler);
      const user = userEvent.setup();
      render(
        <AdaptiveHintCallout
          adaptation={makeAdaptation("show_hint", "Hint body")}
          onDismiss={vi.fn()}
        />,
      );
      const region = screen.getByRole("complementary", { name: "Learning hint" });
      region.focus();
      await user.keyboard("{Escape}");
      // nativeEvent.stopImmediatePropagation() prevents the event reaching window listeners.
      expect(windowHandler).not.toHaveBeenCalled();
      window.removeEventListener("keydown", windowHandler);
    });

    it("restores the same content when 'Show hint' is clicked", async () => {
      const user = userEvent.setup();
      render(
        <AdaptiveHintCallout
          adaptation={makeAdaptation("show_hint", "Restorable hint body")}
          onDismiss={vi.fn()}
        />,
      );
      await user.click(screen.getByRole("button", { name: "Dismiss hint" }));
      expect(screen.queryByText("Restorable hint body")).not.toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Show hint" }));
      expect(screen.getByText("Restorable hint body")).toBeInTheDocument();
      expect(screen.getByRole("complementary", { name: "Learning hint" })).toBeInTheDocument();
    });
  });

  describe("accessibility", () => {
    it("exposes role=complementary, aria-label and is focusable", () => {
      render(
        <AdaptiveHintCallout adaptation={makeAdaptation("show_hint", "x")} onDismiss={vi.fn()} />,
      );
      const region = screen.getByRole("complementary", { name: "Learning hint" });
      expect(region).toHaveAttribute("tabindex", "0");
    });

    it("keeps role/label on the encouragement variant even without a box", () => {
      render(
        <AdaptiveHintCallout
          adaptation={makeAdaptation("show_encouragement", "Great job")}
          onDismiss={vi.fn()}
        />,
      );
      expect(screen.getByRole("complementary", { name: "Learning hint" })).toBeInTheDocument();
    });

    it("dismiss and 'Show hint' controls are real buttons with accessible names", async () => {
      const user = userEvent.setup();
      render(
        <AdaptiveHintCallout adaptation={makeAdaptation("show_hint", "x")} onDismiss={vi.fn()} />,
      );
      expect(screen.getByRole("button", { name: "Dismiss hint" })).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Dismiss hint" }));
      expect(screen.getByRole("button", { name: "Show hint" })).toBeInTheDocument();
    });
  });

  describe("reduced motion", () => {
    it("dismisses instantly (no JS-timed delay) when prefers-reduced-motion is reduce", async () => {
      stubMatchMedia(true);
      const onDismiss = vi.fn();
      const user = userEvent.setup();
      render(
        <AdaptiveHintCallout adaptation={makeAdaptation("show_hint", "x")} onDismiss={onDismiss} />,
      );
      await user.click(screen.getByRole("button", { name: "Dismiss hint" }));
      // No fake timers advanced — under reduced motion the affordance is shown synchronously.
      expect(screen.getByRole("button", { name: "Show hint" })).toBeInTheDocument();
      expect(onDismiss).toHaveBeenCalledTimes(1);
    });

    it("defers dismissal via a JS-timed fade-out when motion is allowed", async () => {
      stubMatchMedia(false);
      const onDismiss = vi.fn();
      const user = userEvent.setup();
      render(
        <AdaptiveHintCallout adaptation={makeAdaptation("show_hint", "x")} onDismiss={onDismiss} />,
      );
      await user.click(screen.getByRole("button", { name: "Dismiss hint" }));
      // With motion allowed the callout fades out first; the dismissed affordance is
      // NOT shown synchronously (unlike the reduced-motion path above).
      expect(screen.queryByRole("button", { name: "Show hint" })).not.toBeInTheDocument();
      // After the fade-out delay it resolves to the dismissed state.
      await waitFor(() => {
        expect(screen.getByRole("button", { name: "Show hint" })).toBeInTheDocument();
      });
      expect(onDismiss).toHaveBeenCalledTimes(1);
    });

    it("renders CSS transition utility classes so the global reduced-motion rule applies", async () => {
      render(
        <AdaptiveHintCallout adaptation={makeAdaptation("show_hint", "x")} onDismiss={vi.fn()} />,
      );
      // After the rAF fires (enter animation), the region is visible.
      const region = await screen.findByRole("complementary", { name: "Learning hint" });
      expect(region.className).toContain("transition-");
      expect(region.className).toContain("duration-300");
    });

    it("starts at opacity-0 on mount and transitions to opacity-100 after rAF (enter animation)", async () => {
      render(
        <AdaptiveHintCallout adaptation={makeAdaptation("show_hint", "x")} onDismiss={vi.fn()} />,
      );
      // Immediately after mount the container starts invisible (opacity-0 translate-y-2).
      const region = screen.getByRole("complementary", { name: "Learning hint" });
      expect(region.className).toContain("opacity-0");
      // After the rAF-deferred visible=true flip, it transitions to fully visible.
      await waitFor(() => {
        expect(region.className).toContain("opacity-100");
      });
    });
  });

  describe("dismiss guard", () => {
    it("calls onDismiss exactly once even if the dismiss button is clicked twice rapidly", async () => {
      stubMatchMedia(false); // motion allowed → JS-timed delay path
      const onDismiss = vi.fn();
      const user = userEvent.setup();
      render(
        <AdaptiveHintCallout adaptation={makeAdaptation("show_hint", "x")} onDismiss={onDismiss} />,
      );
      const btn = screen.getByRole("button", { name: "Dismiss hint" });
      // Fire two rapid clicks; the guard (leaving || dismissed) prevents the second from
      // setting a second timer so onDismiss is called exactly once.
      await user.click(btn);
      await user.click(btn);
      await waitFor(() => {
        expect(screen.getByRole("button", { name: "Show hint" })).toBeInTheDocument();
      });
      expect(onDismiss).toHaveBeenCalledTimes(1);
    });
  });
});
