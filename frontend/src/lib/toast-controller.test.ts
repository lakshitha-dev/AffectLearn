import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

// Mock `sonner` so we can capture which method is called and with what options (duration +
// the onAutoClose/onDismiss callbacks the governor uses to free a slot).
const mocks = vi.hoisted(() => ({
  success: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
  base: vi.fn(),
  dismiss: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: Object.assign(mocks.base, {
    success: mocks.success,
    info: mocks.info,
    warning: mocks.warning,
    error: mocks.error,
    dismiss: mocks.dismiss,
  }),
  Toaster: () => null,
}));

import { enqueueToast, resetToastController, makeToastId } from "./toast-controller";
import { useNotificationStore, type ToastLevel } from "@/stores/notification-store";

function spec(level: ToastLevel, message: string, id = makeToastId()) {
  return { id, level, message };
}

/** Pull the options object out of the most recent call to a mocked toast method. */
type ToastOpts = { duration: number; onAutoClose: () => void; onDismiss: () => void };
function lastOptsOf(fn: ReturnType<typeof vi.fn>): ToastOpts {
  const call = fn.mock.calls.at(-1);
  return call![1] as ToastOpts;
}

beforeEach(() => {
  vi.useFakeTimers();
  mocks.success.mockReset();
  mocks.info.mockReset();
  mocks.warning.mockReset();
  mocks.error.mockReset();
  mocks.base.mockReset();
  mocks.dismiss.mockReset();
  resetToastController();
});

afterEach(() => {
  resetToastController();
  vi.useRealTimers();
});

describe("toast-controller", () => {
  describe("severity → sonner call + duration mapping (AC2/AC5)", () => {
    it("success routes through toast.success with duration 3000", () => {
      enqueueToast(spec("success", "Saved."));
      expect(mocks.success).toHaveBeenCalledTimes(1);
      expect(mocks.success).toHaveBeenCalledWith(
        "Saved.",
        expect.objectContaining({ duration: 3000 }),
      );
    });

    it("info routes through toast.info with duration 3000", () => {
      enqueueToast(spec("info", "Heads up."));
      expect(mocks.info).toHaveBeenCalledWith(
        "Heads up.",
        expect.objectContaining({ duration: 3000 }),
      );
    });

    it("warning routes through toast.warning with duration 3000", () => {
      enqueueToast(spec("warning", "Careful."));
      expect(mocks.warning).toHaveBeenCalledWith(
        "Careful.",
        expect.objectContaining({ duration: 3000 }),
      );
    });

    it("error routes through toast.error with duration Infinity (persists)", () => {
      enqueueToast(spec("error", "Boom."));
      expect(mocks.error).toHaveBeenCalledTimes(1);
      expect(mocks.error).toHaveBeenCalledWith(
        "Boom.",
        expect.objectContaining({ duration: Infinity }),
      );
    });

    it("an error toast never auto-dismisses on a timer (duration Infinity, no scheduled close)", () => {
      enqueueToast(spec("error", "Boom."));
      // Advancing time must not free the slot — visibleCount stays 1, no further sonner calls.
      vi.advanceTimersByTime(60_000);
      expect(useNotificationStore.getState().visibleCount).toBe(1);
      expect(mocks.error).toHaveBeenCalledTimes(1);
    });
  });

  describe("max-2 stacking + 500ms queue release (AC3)", () => {
    it("releases only 2 toasts immediately when 3 are enqueued", () => {
      enqueueToast(spec("info", "A"));
      enqueueToast(spec("info", "B"));
      enqueueToast(spec("info", "C"));

      // Only A and B are shown; C waits in the queue.
      expect(mocks.info).toHaveBeenCalledTimes(2);
      expect(useNotificationStore.getState().visibleCount).toBe(2);
      expect(useNotificationStore.getState().queue.map((s) => s.message)).toEqual(["C"]);
    });

    it("releases the 3rd (FIFO) only after a slot frees AND 500ms elapses", () => {
      enqueueToast(spec("info", "A"));
      enqueueToast(spec("info", "B"));
      enqueueToast(spec("info", "C"));
      expect(mocks.info).toHaveBeenCalledTimes(2);

      // Free one slot by firing A's auto-close callback.
      const aOpts = mocks.info.mock.calls[0][1] as ToastOpts;
      aOpts.onAutoClose();

      // Slot is free but <500ms since the last release — C must NOT appear yet.
      expect(mocks.info).toHaveBeenCalledTimes(2);
      expect(useNotificationStore.getState().visibleCount).toBe(1);

      // Advance the 500ms spacing → C is released (FIFO).
      vi.advanceTimersByTime(500);
      expect(mocks.info).toHaveBeenCalledTimes(3);
      expect(mocks.info.mock.calls[2][0]).toBe("C");
      expect(useNotificationStore.getState().queue).toEqual([]);
    });

    it("never exceeds 2 visible across a burst of dismissals + releases", () => {
      for (const m of ["A", "B", "C", "D", "E"]) enqueueToast(spec("info", m));
      expect(useNotificationStore.getState().visibleCount).toBe(2);

      // Dismiss + advance repeatedly; assert the cap holds at every step.
      for (let i = 0; i < 3; i++) {
        const opts = lastOptsOf(mocks.info);
        opts.onDismiss();
        expect(useNotificationStore.getState().visibleCount).toBeLessThanOrEqual(2);
        vi.advanceTimersByTime(500);
        expect(useNotificationStore.getState().visibleCount).toBeLessThanOrEqual(2);
      }
      // All five eventually released, in FIFO order.
      expect(mocks.info).toHaveBeenCalledTimes(5);
      expect(mocks.info.mock.calls.map((c) => c[0])).toEqual(["A", "B", "C", "D", "E"]);
    });
  });

  describe("timer cleanup (AC3 — no late release after reset)", () => {
    it("resetToastController clears the pending release timer", () => {
      enqueueToast(spec("info", "A"));
      enqueueToast(spec("info", "B"));
      enqueueToast(spec("info", "C"));
      // Free a slot to schedule a pending release of C.
      (mocks.info.mock.calls[0][1] as ToastOpts).onDismiss();

      resetToastController();
      mocks.info.mockClear();

      // Advancing time after reset must NOT release C (timer was cleared, state zeroed).
      vi.advanceTimersByTime(5000);
      expect(mocks.info).not.toHaveBeenCalled();
      expect(useNotificationStore.getState().visibleCount).toBe(0);
      expect(useNotificationStore.getState().queue).toEqual([]);
    });
  });
});
