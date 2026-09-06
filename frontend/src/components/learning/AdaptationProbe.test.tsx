import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AdaptationProbe, probeTarget, PROBE_DELAY_MS } from "./AdaptationProbe";
import { useAdaptationStore } from "@/stores/adaptation-store";
import type { AdaptationAction } from "@/types/ws-messages";

let seq = 0;
function seed(action: AdaptationAction, receivedAt = Date.now()) {
  seq += 1;
  const id = `probe-${seq}`;
  useAdaptationStore.getState().pushAdaptation({ id, action, text: "x", receivedAt });
  return id;
}

describe("AdaptationProbe", () => {
  beforeEach(() => {
    useAdaptationStore.getState().reset();
    seq = 0;
  });

  it("shows nothing before the delay has elapsed", () => {
    seed("show_hint");
    const { container } = render(<AdaptationProbe delayMs={10_000} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("appears once the delay has elapsed", async () => {
    vi.useFakeTimers();
    try {
      seed("show_hint");
      render(<AdaptationProbe delayMs={1000} />);
      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(screen.getByText("Did that help?")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("waits 30 seconds by default, so the answer is about the help and not the interruption", () => {
    // Asking immediately would measure the learner's reaction to being interrupted.
    expect(PROBE_DELAY_MS).toBe(30_000);
  });

  it("records each of the three answers", async () => {
    for (const [label, expected] of [
      ["Yes, that helped", "helped"],
      ["Not really", "did_not_help"],
      ["Not sure", "unsure"],
    ] as const) {
      useAdaptationStore.getState().reset();
      const id = seed("show_hint", Date.now() - 60_000); // already past the delay
      const onRespond = vi.fn();
      const { unmount } = render(<AdaptationProbe onRespond={onRespond} delayMs={0} />);

      await userEvent.click(await screen.findByText(label));

      expect(onRespond).toHaveBeenCalledWith(
        expect.objectContaining({ adaptation_id: id, response: expected, dismissed: false }),
      );
      unmount();
    }
  });

  it("reports a skip as dismissed with no response", async () => {
    // Declining to appraise is NOT a negative appraisal. Collapsing the two would manufacture
    // negative evidence about interventions the learner never judged.
    seed("show_hint", Date.now() - 60_000);
    const onRespond = vi.fn();
    render(<AdaptationProbe onRespond={onRespond} delayMs={0} />);

    await userEvent.click(await screen.findByLabelText("Dismiss this question"));

    expect(onRespond).toHaveBeenCalledWith(
      expect.objectContaining({ response: null, dismissed: true }),
    );
  });

  it("reports how long the intervention was on screen", async () => {
    seed("show_hint", Date.now() - 45_000);
    const onRespond = vi.fn();
    render(<AdaptationProbe onRespond={onRespond} delayMs={0} />);

    await userEvent.click(await screen.findByText("Yes, that helped"));

    const { shown_after_ms } = onRespond.mock.calls[0][0];
    expect(shown_after_ms).toBeGreaterThanOrEqual(45_000);
  });

  it("asks about a given intervention only once", async () => {
    // Re-asking would train the learner to dismiss reflexively, and every later answer would be
    // about the annoyance rather than about the help.
    seed("show_hint", Date.now() - 60_000);
    render(<AdaptationProbe delayMs={0} />);

    await userEvent.click(await screen.findByText("Not sure"));

    expect(screen.queryByText("Did that help?")).not.toBeInTheDocument();
  });
});

describe("which interventions get probed", () => {
  beforeEach(() => {
    useAdaptationStore.getState().reset();
    seq = 0;
  });

  it.each(["show_hint", "show_alternative", "show_breakdown", "simplify", "increase_difficulty"])(
    "probes %s, which puts content in front of the learner",
    (action) => {
      seed(action as AdaptationAction);
      expect(probeTarget(useAdaptationStore.getState().adaptationQueue)?.action).toBe(action);
    },
  );

  it("does not probe skip_ahead, which is navigation rather than help", () => {
    // "Did that help?" after a page advance asks a different question, and mixing the two would
    // dilute the measure the study depends on.
    seed("skip_ahead");
    expect(probeTarget(useAdaptationStore.getState().adaptationQueue)).toBeNull();
  });

  it("does not probe suggest_break, which is answered by whether the learner returns", () => {
    seed("suggest_break");
    expect(probeTarget(useAdaptationStore.getState().adaptationQueue)).toBeNull();
  });

  it("probes the most recent content intervention when several have arrived", () => {
    seed("show_hint");
    const latest = seed("show_breakdown");
    expect(probeTarget(useAdaptationStore.getState().adaptationQueue)?.id).toBe(latest);
  });
});
