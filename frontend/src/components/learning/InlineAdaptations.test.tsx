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

describe("actions that previously reached no learner", () => {
  beforeEach(() => {
    useAdaptationStore.getState().reset();
    seq = 0;
    stubMatchMedia(true);
  });

  it("renders simplify, which had no consumer anywhere in the routing matrix", () => {
    // It is the rule-based fallback for `frustrated`, so on a degraded LLM the most distressed
    // learner in the system was the one guaranteed to receive silence.
    seed("simplify", "Let's take this more gently.");
    render(<InlineAdaptations />);
    expect(screen.getByText("Let's take this more gently.")).toBeInTheDocument();
  });

  it("renders increase_difficulty, which used to render null", () => {
    // Its consumer selected against a harder-content catalogue that does not exist, so a bored
    // learner got an empty box. It is generative text now.
    seed("increase_difficulty", "Why would this break for an empty list?");
    render(<InlineAdaptations />);
    expect(screen.getByText("Why would this break for an empty list?")).toBeInTheDocument();
  });
});

describe("assistance attribution is narrower than what is rendered", () => {
  beforeEach(() => {
    useAdaptationStore.getState().reset();
    seq = 0;
    stubMatchMedia(true);
  });

  it("does not attribute a quiz answer to a challenge question", async () => {
    // `increase_difficulty` shares the callout surface but is the opposite intervention: it asks
    // the learner something harder rather than helping with this one. Counting it as assistance
    // would merge "was the learner helped before answering" with "was the learner challenged
    // before answering" into one column, and neither question could then be asked of it.
    const { activeInlineAdaptation } = await import("./InlineAdaptations");
    seed("increase_difficulty", "A harder question.");
    expect(activeInlineAdaptation(useAdaptationStore.getState().adaptationQueue)).toBeNull();
  });

  it("still attributes a quiz answer to a hint that preceded it", async () => {
    const { activeInlineAdaptation } = await import("./InlineAdaptations");
    seed("show_hint", "Try relating it to something you know.");
    const active = activeInlineAdaptation(useAdaptationStore.getState().adaptationQueue);
    expect(active?.action).toBe("show_hint");
  });

  it("counts simplify as assistance, because it genuinely is help", async () => {
    const { activeInlineAdaptation } = await import("./InlineAdaptations");
    seed("simplify", "Here it is in simpler terms.");
    expect(
      activeInlineAdaptation(useAdaptationStore.getState().adaptationQueue)?.action,
    ).toBe("simplify");
  });

  it("a challenge shown after a hint does not displace the hint as the assistance", async () => {
    const { activeInlineAdaptation, activeRenderableAdaptation } = await import(
      "./InlineAdaptations"
    );
    seed("show_hint", "The hint.");
    seed("increase_difficulty", "The challenge.");
    const queue = useAdaptationStore.getState().adaptationQueue;

    // The challenge is what is on screen...
    expect(activeRenderableAdaptation(queue)?.action).toBe("increase_difficulty");
    // ...but the hint is still what any subsequent answer is attributed to.
    expect(activeInlineAdaptation(queue)?.action).toBe("show_hint");
  });
});
