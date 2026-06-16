import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SkipAheadSuggestion } from "./SkipAheadSuggestion";
import { useAdaptationStore } from "@/stores/adaptation-store";
import type { AdaptationAction } from "@/types/ws-messages";

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

let idCounter = 0;
function push(action: AdaptationAction, text?: string) {
  idCounter += 1;
  useAdaptationStore.getState().pushAdaptation({
    id: `id-${action}-${idCounter}`,
    action,
    text,
    receivedAt: Date.now(),
  });
}

const COPY = "Looks like you've got this — skip to the challenge exercise?";

describe("SkipAheadSuggestion", () => {
  beforeEach(() => {
    useAdaptationStore.getState().reset();
    idCounter = 0;
    stubMatchMedia(true); // reduced motion → synchronous accept/dismiss
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders nothing when the queue is empty", () => {
    const { container } = render(
      <SkipAheadSuggestion onSkip={vi.fn()} onInteraction={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the suggestion for a pushed skip_ahead adaptation", () => {
    push("skip_ahead");
    render(<SkipAheadSuggestion onSkip={vi.fn()} onInteraction={vi.fn()} />);
    expect(screen.getByText(COPY)).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Skip ahead suggestion" })).toBeInTheDocument();
  });

  it("accept invokes onSkip (nav) and logs an 'accepted' interaction once", async () => {
    push("skip_ahead");
    const onSkip = vi.fn();
    const onInteraction = vi.fn();
    const user = userEvent.setup();
    render(<SkipAheadSuggestion onSkip={onSkip} onInteraction={onInteraction} />);
    await user.click(screen.getByRole("button", { name: "Skip ahead" }));
    expect(onSkip).toHaveBeenCalledTimes(1);
    expect(onInteraction).toHaveBeenCalledTimes(1);
    const [id, interaction] = onInteraction.mock.calls[0];
    expect(id).toMatch(/^id-skip_ahead/);
    expect(interaction).toBe("accepted");
  });

  it("dismiss logs a 'dismissed' interaction and does NOT advance the section", async () => {
    push("skip_ahead");
    const onSkip = vi.fn();
    const onInteraction = vi.fn();
    const user = userEvent.setup();
    render(<SkipAheadSuggestion onSkip={onSkip} onInteraction={onInteraction} />);
    await user.click(screen.getByRole("button", { name: "Not now" }));
    expect(onSkip).not.toHaveBeenCalled();
    expect(onInteraction).toHaveBeenCalledTimes(1);
    expect(onInteraction.mock.calls[0][1]).toBe("dismissed");
  });

  it("ignores non-skip_ahead items and leaves them in the queue", () => {
    // `simplify` (5.4-adjacent) + `suggest_break` (5.5) + `show_hint` (5.4) are all non-owned
    // AdaptationActions; `increase_difficulty` is owned by the sibling UI-less consumer, not
    // this one. (`notification` is a separate downstream message type, never an Adaptation, so
    // it never enters this queue.)
    push("show_hint", "a hint");
    push("suggest_break");
    push("simplify");
    push("increase_difficulty");
    const { container } = render(
      <SkipAheadSuggestion onSkip={vi.fn()} onInteraction={vi.fn()} />,
    );
    // Nothing rendered by SkipAheadSuggestion for these actions.
    expect(container).toBeEmptyDOMElement();
    // And they are all left untouched in the queue for 5.4/5.5/5.7 (and the sibling consumer).
    const actions = useAdaptationStore.getState().adaptationQueue.map((a) => a.action);
    expect(actions).toEqual(["show_hint", "suggest_break", "simplify", "increase_difficulty"]);
  });

  it("renders only the LATEST skip_ahead when several are queued", () => {
    push("skip_ahead", "first");
    push("show_hint");
    push("skip_ahead", "second");
    render(<SkipAheadSuggestion onSkip={vi.fn()} onInteraction={vi.fn()} />);
    // Single active suggestion; queue is never mutated.
    expect(screen.getAllByText(COPY)).toHaveLength(1);
    expect(useAdaptationStore.getState().adaptationQueue).toHaveLength(3);
  });
});
