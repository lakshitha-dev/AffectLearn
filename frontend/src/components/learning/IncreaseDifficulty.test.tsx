import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";

import { IncreaseDifficulty } from "./IncreaseDifficulty";
import { useAdaptationStore } from "@/stores/adaptation-store";
import type { AdaptationAction } from "@/types/ws-messages";

let idCounter = 0;
function push(action: AdaptationAction) {
  idCounter += 1;
  useAdaptationStore.getState().pushAdaptation({
    id: `id-${action}-${idCounter}`,
    action,
    receivedAt: Date.now(),
  });
}

describe("IncreaseDifficulty", () => {
  beforeEach(() => {
    useAdaptationStore.getState().reset();
    idCounter = 0;
  });

  it("renders nothing (invisible swap, UX spec line 675)", () => {
    push("increase_difficulty");
    const { container } = render(<IncreaseDifficulty onApplied={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("fires the applied log exactly once for a pushed increase_difficulty", () => {
    push("increase_difficulty");
    const onApplied = vi.fn();
    render(<IncreaseDifficulty onApplied={onApplied} />);
    expect(onApplied).toHaveBeenCalledTimes(1);
    expect(onApplied.mock.calls[0][0]).toMatch(/^id-increase_difficulty/);
  });

  it("does NOT re-log on re-render (idempotent per id, AC7)", () => {
    push("increase_difficulty");
    const onApplied = vi.fn();
    const { rerender } = render(<IncreaseDifficulty onApplied={onApplied} />);
    rerender(<IncreaseDifficulty onApplied={onApplied} />);
    rerender(<IncreaseDifficulty onApplied={onApplied} />);
    expect(onApplied).toHaveBeenCalledTimes(1);
  });

  it("does not log for non-increase_difficulty items", () => {
    push("skip_ahead");
    push("show_hint");
    push("suggest_break");
    const onApplied = vi.fn();
    render(<IncreaseDifficulty onApplied={onApplied} />);
    expect(onApplied).not.toHaveBeenCalled();
    // Non-owned items are left untouched in the queue.
    expect(useAdaptationStore.getState().adaptationQueue).toHaveLength(3);
  });

  it("is a pure no-op when onApplied is omitted", () => {
    push("increase_difficulty");
    const { container } = render(<IncreaseDifficulty />);
    expect(container).toBeEmptyDOMElement();
  });
});
