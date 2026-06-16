import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

import { BreakSuggestion } from "./BreakSuggestion";
import { useAdaptationStore } from "@/stores/adaptation-store";
import type { Adaptation } from "@/stores/adaptation-store";
import type { AdaptationAction } from "@/types/ws-messages";

function makeAdaptation(action: AdaptationAction, id: string, text?: string): Adaptation {
  return { id, action, text, receivedAt: Date.now() };
}

/** Stub jsdom's missing window.matchMedia (the card uses useReducedMotion). */
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

describe("BreakSuggestion consumer", () => {
  beforeEach(() => {
    stubMatchMedia(true);
    useAdaptationStore.getState().reset();
  });

  it("renders nothing when the queue is empty", () => {
    const { container } = render(<BreakSuggestion />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("renders a BreakSuggestionCard for a suggest_break item", () => {
    useAdaptationStore.getState().pushAdaptation(makeAdaptation("suggest_break", "b1"));
    render(<BreakSuggestion />);
    expect(screen.getByRole("alertdialog", { name: "Break suggestion" })).toBeInTheDocument();
  });

  it("ignores a show_hint item, renders nothing, and leaves it in the queue", () => {
    useAdaptationStore.getState().pushAdaptation(makeAdaptation("show_hint", "h1", "A hint"));
    render(<BreakSuggestion />);
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    // The non-owned item is left untouched in the queue for 5.4 to consume.
    const queue = useAdaptationStore.getState().adaptationQueue;
    expect(queue).toHaveLength(1);
    expect(queue[0].action).toBe("show_hint");
  });

  it("renders the LATEST suggest_break when multiple exist", () => {
    useAdaptationStore.getState().pushAdaptation(makeAdaptation("suggest_break", "b1"));
    useAdaptationStore.getState().pushAdaptation(makeAdaptation("show_hint", "h1"));
    useAdaptationStore.getState().pushAdaptation(makeAdaptation("suggest_break", "b2"));
    render(<BreakSuggestion />);
    // One overlay only; the show_hint stays untouched in the queue.
    expect(screen.getAllByRole("alertdialog")).toHaveLength(1);
    expect(useAdaptationStore.getState().adaptationQueue).toHaveLength(3);
  });

  it("does not mutate the queue when a break card is rendered", () => {
    useAdaptationStore.getState().pushAdaptation(makeAdaptation("suggest_break", "b1"));
    render(<BreakSuggestion />);
    expect(useAdaptationStore.getState().adaptationQueue).toHaveLength(1);
  });
});
