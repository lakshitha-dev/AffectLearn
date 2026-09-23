import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AdaptiveHintCallout } from "./AdaptiveHintCallout";
import type { Adaptation } from "@/stores/adaptation-store";
import type { AdaptationAction } from "@/types/ws-messages";

function makeAdaptation(action: AdaptationAction, text = "Some help text."): Adaptation {
  return { id: `id-${action}`, action, text, receivedAt: Date.now() };
}

beforeEach(() => {
  // Reduced motion ON so a dismiss completes synchronously.
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

describe("AdaptiveHintCallout response buttons", () => {
  it("shows no buttons when no request handler is supplied (unchanged behaviour)", () => {
    render(<AdaptiveHintCallout adaptation={makeAdaptation("show_hint")} onDismiss={() => {}} />);
    expect(screen.queryByRole("button", { name: "Still stuck" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Got it" })).toBeNull();
  });

  it("'Still stuck' on a hint requests the next confusion step and locks the card", async () => {
    const onRequest = vi.fn();
    render(
      <AdaptiveHintCallout
        adaptation={makeAdaptation("show_hint")}
        onDismiss={() => {}}
        onRequest={onRequest}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Still stuck" }));
    expect(onRequest).toHaveBeenCalledWith("still_stuck");
    expect(screen.getByRole("status")).toHaveTextContent("Finding another way to help");
    expect(screen.queryByRole("button", { name: "Still stuck" })).toBeNull();
  });

  it("'Got it' reports success and dismisses", async () => {
    const onGotIt = vi.fn();
    const onDismiss = vi.fn();
    render(
      <AdaptiveHintCallout
        adaptation={makeAdaptation("show_breakdown", "1. First\n2. Second")}
        onDismiss={onDismiss}
        onRequest={() => {}}
        onGotIt={onGotIt}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Got it" }));
    expect(onGotIt).toHaveBeenCalledOnce();
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("a challenge card offers a hint or a way forward instead", async () => {
    const onRequest = vi.fn();
    render(
      <AdaptiveHintCallout
        adaptation={makeAdaptation("increase_difficulty")}
        onDismiss={() => {}}
        onRequest={onRequest}
      />,
    );
    expect(screen.queryByRole("button", { name: "Got it" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "I'd rather move on" }));
    expect(onRequest).toHaveBeenCalledWith("move_on");
  });

  it("'Give me a hint' on a challenge climbs the confusion ladder", async () => {
    const onRequest = vi.fn();
    render(
      <AdaptiveHintCallout
        adaptation={makeAdaptation("increase_difficulty")}
        onDismiss={() => {}}
        onRequest={onRequest}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Give me a hint" }));
    expect(onRequest).toHaveBeenCalledWith("still_stuck");
  });

  it("encouragement stays a plain line with no buttons", () => {
    render(
      <AdaptiveHintCallout
        adaptation={makeAdaptation("show_encouragement")}
        onDismiss={() => {}}
        onRequest={() => {}}
      />,
    );
    expect(screen.queryAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual([
      "Dismiss hint",
    ]);
  });
});
