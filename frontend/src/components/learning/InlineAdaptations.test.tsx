import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { InlineAdaptations } from "./InlineAdaptations";
import { useAdaptationStore } from "@/stores/adaptation-store";
import type { AdaptationAction } from "@/types/ws-messages";

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

let seq = 0;
function seed(action: AdaptationAction, text?: string) {
  seq += 1;
  useAdaptationStore.getState().pushAdaptation({
    id: `seed-${seq}`,
    action,
    text,
    receivedAt: Date.now() + seq,
  });
}

describe("InlineAdaptations", () => {
  beforeEach(() => {
    useAdaptationStore.getState().reset();
    seq = 0;
    stubMatchMedia(true);
  });

  it("renders nothing when the queue is empty", () => {
    const { container } = render(<InlineAdaptations />);
    expect(container.firstChild).toBeNull();
  });

  it("renders one callout for a seeded show_hint item", () => {
    seed("show_hint", "Here is a hint.");
    render(<InlineAdaptations />);
    expect(screen.getByRole("complementary", { name: "Learning hint" })).toBeInTheDocument();
    expect(screen.getByText("Here is a hint.")).toBeInTheDocument();
  });

  it("ignores non-show_* actions and leaves them in the queue", () => {
    seed("suggest_break");
    seed("skip_ahead");
    const { container } = render(<InlineAdaptations />);
    expect(container.firstChild).toBeNull();
    // Items remain in the queue for Stories 5.5–5.7.
    expect(useAdaptationStore.getState().adaptationQueue).toHaveLength(2);
  });

  it("renders only the latest inline adaptation when several are queued", () => {
    seed("show_hint", "Older hint");
    seed("show_alternative", "Newest alternative");
    render(<InlineAdaptations />);
    expect(screen.getByText("Newest alternative")).toBeInTheDocument();
    expect(screen.queryByText("Older hint")).not.toBeInTheDocument();
  });

  it("skips non-inline items and renders the latest inline one", () => {
    seed("show_hint", "The inline hint");
    seed("suggest_break");
    render(<InlineAdaptations />);
    expect(screen.getByText("The inline hint")).toBeInTheDocument();
    expect(useAdaptationStore.getState().adaptationQueue).toHaveLength(2);
  });

  it("does not mutate the queue on dismiss (local UI state only)", async () => {
    seed("show_hint", "Dismissable hint");
    const user = userEvent.setup();
    render(<InlineAdaptations />);
    await user.click(screen.getByRole("button", { name: "Dismiss hint" }));
    // Dismissed locally → 'Show hint' affordance, but the item stays in the queue.
    expect(screen.getByRole("button", { name: "Show hint" })).toBeInTheDocument();
    expect(useAdaptationStore.getState().adaptationQueue).toHaveLength(1);
  });
});
