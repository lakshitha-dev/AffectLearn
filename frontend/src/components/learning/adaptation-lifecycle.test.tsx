import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, act, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AdaptationProbe } from "./AdaptationProbe";
import { AdaptiveHintCallout } from "./AdaptiveHintCallout";
import { BreakSuggestionCard } from "./BreakSuggestionCard";
import { ExerciseBlock } from "./ExerciseBlock";
import { useAdaptationStore, type Adaptation } from "@/stores/adaptation-store";

// Card lifecycle facts for the research record. None of them is the learner's verdict on a card;
// each is reported once, through `onLifecycle`, and changes nothing the learner sees.

function adaptation(action: Adaptation["action"], id = "ad-1"): Adaptation {
  return { id, action, text: "Step one\nStep two", receivedAt: Date.now() - 60_000 };
}

describe("AdaptationProbe lifecycle", () => {
  beforeEach(() => useAdaptationStore.getState().reset());

  it("reports when the question is shown, once", async () => {
    useAdaptationStore.getState().pushAdaptation(adaptation("show_hint"));
    const onLifecycle = vi.fn();
    render(<AdaptationProbe delayMs={0} onLifecycle={onLifecycle} />);
    await screen.findByText("Did that help?");
    // Passive effects flush after the DOM update the query waited for.
    await waitFor(() => expect(onLifecycle).toHaveBeenCalledTimes(1));
    expect(onLifecycle.mock.calls[0][0]).toMatchObject({
      adaptation_id: "ad-1", action: "show_hint", event: "probe_shown",
    });
  });

  it("reports a question left unanswered when the page goes away", async () => {
    useAdaptationStore.getState().pushAdaptation(adaptation("show_hint"));
    const onLifecycle = vi.fn();
    const { unmount } = render(<AdaptationProbe delayMs={0} onLifecycle={onLifecycle} />);
    await screen.findByText("Did that help?");
    unmount();
    expect(onLifecycle.mock.calls.map((c) => c[0].event)).toEqual(["probe_shown", "probe_unanswered"]);
  });

  it("does not report an answered question as unanswered", async () => {
    useAdaptationStore.getState().pushAdaptation(adaptation("show_hint"));
    const onLifecycle = vi.fn();
    const { unmount } = render(
      <AdaptationProbe delayMs={0} onLifecycle={onLifecycle} onRespond={vi.fn()} />,
    );
    await userEvent.click(await screen.findByText("Not sure"));
    unmount();
    expect(onLifecycle.mock.calls.map((c) => c[0].event)).toEqual(["probe_shown"]);
  });

  it("reports the old question unanswered when a newer card replaces it", async () => {
    useAdaptationStore.getState().pushAdaptation(adaptation("show_hint", "ad-1"));
    const onLifecycle = vi.fn();
    render(<AdaptationProbe delayMs={0} onLifecycle={onLifecycle} />);
    await screen.findByText("Did that help?");
    act(() => {
      useAdaptationStore.getState().pushAdaptation(adaptation("show_breakdown", "ad-2"));
    });
    await screen.findByText("Did that help?");
    const events = onLifecycle.mock.calls.map((c) => `${c[0].adaptation_id}:${c[0].event}`);
    expect(events).toEqual(["ad-1:probe_shown", "ad-1:probe_unanswered", "ad-2:probe_shown"]);
  });
});

describe("AdaptiveHintCallout lifecycle", () => {
  it("reports that the card was rendered, once", () => {
    const onLifecycle = vi.fn();
    const { rerender } = render(
      <AdaptiveHintCallout adaptation={adaptation("show_hint")} onDismiss={vi.fn()}
        onLifecycle={onLifecycle} />,
    );
    rerender(
      <AdaptiveHintCallout adaptation={adaptation("show_hint")} onDismiss={vi.fn()}
        onLifecycle={onLifecycle} />,
    );
    expect(onLifecycle.mock.calls.filter((c) => c[0] === "rendered")).toHaveLength(1);
  });

  it("reports a breakdown being collapsed and expanded", () => {
    const onLifecycle = vi.fn();
    render(
      <AdaptiveHintCallout adaptation={adaptation("show_breakdown")} onDismiss={vi.fn()}
        onLifecycle={onLifecycle} />,
    );
    const toggle = document.querySelector('[data-track="adaptation-expand"]') as HTMLElement;
    fireEvent.click(toggle); // starts expanded
    fireEvent.click(toggle);
    expect(onLifecycle.mock.calls.map((c) => c[0])).toEqual(["rendered", "collapsed", "expanded"]);
  });
});

describe("BreakSuggestionCard lifecycle", () => {
  it("reports a break taken and an early return with the time away", () => {
    vi.useFakeTimers();
    try {
      const onLifecycle = vi.fn();
      render(
        <BreakSuggestionCard adaptation={adaptation("suggest_break")} onDismiss={vi.fn()}
          breakSeconds={60} onLifecycle={onLifecycle} />,
      );
      fireEvent.click(screen.getByText("Take a break"));
      act(() => vi.advanceTimersByTime(20_000));
      fireEvent.click(screen.getByText("I'm ready, continue"));
      expect(onLifecycle.mock.calls[0]).toEqual(["break_taken"]);
      expect(onLifecycle.mock.calls[1][0]).toBe("break_returned_early");
      expect(onLifecycle.mock.calls[1][1].seconds_away).toBe(20);
    } finally {
      vi.useRealTimers();
    }
  });

  it("reports a declined break", () => {
    const onLifecycle = vi.fn();
    render(
      <BreakSuggestionCard adaptation={adaptation("suggest_break")} onDismiss={vi.fn()}
        onLifecycle={onLifecycle} />,
    );
    fireEvent.click(document.querySelector('[data-track="break-decline"]') as HTMLElement);
    expect(onLifecycle).toHaveBeenCalledWith("break_declined");
  });

  it("reports a break that ran its full length", () => {
    vi.useFakeTimers();
    try {
      const onLifecycle = vi.fn();
      render(
        <BreakSuggestionCard adaptation={adaptation("suggest_break")} onDismiss={vi.fn()}
          breakSeconds={3} onLifecycle={onLifecycle} />,
      );
      fireEvent.click(screen.getByText("Take a break"));
      act(() => vi.advanceTimersByTime(4_000));
      expect(onLifecycle).toHaveBeenCalledWith("break_completed", { seconds_away: 3 });
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("ExerciseBlock submission", () => {
  it("submits the answer with correctness and time taken", () => {
    vi.useFakeTimers();
    try {
      const onSubmit = vi.fn();
      render(
        <ExerciseBlock blockId="blk-1" onSubmit={onSubmit}
          content={{ prompt: "Name it", answer: "ReAct", type: "text" }} />,
      );
      act(() => vi.advanceTimersByTime(4_000));
      fireEvent.change(screen.getByPlaceholderText("Your answer…"), { target: { value: "react" } });
      fireEvent.click(screen.getByText("Submit"));
      expect(onSubmit).toHaveBeenCalledWith("blk-1", "react", true, 4_000);
    } finally {
      vi.useRealTimers();
    }
  });
});
