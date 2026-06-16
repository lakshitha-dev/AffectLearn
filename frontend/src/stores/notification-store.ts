/**
 * Notification store — ephemeral client-side queue/governor for system toasts (Story 5.7).
 *
 * Story 5.7 is the toast layer: `notification` and `system.{mode_switch|error|reconnected}`
 * WS messages surface as a `sonner` toast (bottom-right). Raw `sonner` stacks unboundedly,
 * but the UX spec (lines 1120-1122) and the Epic-5 AC require: never more than 2 toasts
 * visible simultaneously, additional toasts queued and released 500ms apart as slots free.
 *
 * This store is the SOURCE OF TRUTH for that invariant — it holds `visibleCount` and the
 * pending `queue`. It is PLUMBING ONLY and contains SYNCHRONOUS setters only: the async
 * 500ms release timer + the actual `sonner` `toast.*` calls live in `lib/toast-controller.ts`
 * (architecture: async lives in hooks/controllers, never in stores). Mirrors the flat,
 * ephemeral, NOT-persisted shape of `adaptation-store.ts` / `connection-store.ts`.
 *
 * Severity → dismissal / a11y (governed by the controller, documented here for context):
 *   - success/info/warning → auto-dismiss 3s, role="status" / aria-live="polite"
 *   - error                → persists until dismissed, role="alert" / aria-live="assertive"
 *
 * Why a SEPARATE store (not folded into `adaptation-store`): the `adaptationQueue` is the
 * adaptive-*content* queue consumed by 5.4–5.6's visual components; the toast queue is an
 * *operational/system* surface with different semantics (max-2, 500ms, severity dismissal).
 * Keeping them separate follows the per-concern store decomposition (same rationale 5.3/4.1
 * used for `connection-store`).
 */

import { create } from "zustand";

/** Toast severity. `error` arrives only from the `system.error` path (the 5.3 `notification`
 *  `level` union is `info | success | warning` — there is no `error` in it). */
export type ToastLevel = "success" | "info" | "warning" | "error";

export interface ToastSpec {
  /** Stable client-generated id (crypto.randomUUID with a counter fallback). */
  id: string;
  level: ToastLevel;
  message: string;
}

/** Hard cap on simultaneously-visible toasts (UX spec line 1122). */
export const MAX_VISIBLE = 2;
/** Minimum spacing between successive toast releases, ms (UX spec line 1122). */
export const QUEUE_DELAY_MS = 500;

interface NotificationState {
  /** How many toasts the controller currently has live in `sonner`. */
  visibleCount: number;
  /** FIFO buffer of specs not yet released to `sonner` (over the max-2 cap). */
  queue: ToastSpec[];
  /** Append a spec to the pending queue (the controller drains it — see toast-controller). */
  enqueue: (spec: ToastSpec) => void;
  /** A live toast was dismissed/auto-closed — decrement the visible count (floor 0). */
  onToastClosed: () => void;
  /** Controller bookkeeping: set the live-toast count directly. */
  setVisibleCount: (n: number) => void;
  /** Controller bookkeeping: replace the pending queue (e.g. after shifting the head). */
  setQueue: (queue: ToastSpec[]) => void;
  /** Clear all state (tests + unmount). */
  reset: () => void;
}

const initialState = {
  visibleCount: 0,
  queue: [] as ToastSpec[],
};

export const useNotificationStore = create<NotificationState>()((set) => ({
  ...initialState,
  enqueue: (spec) => set((s) => ({ queue: [...s.queue, spec] })),
  onToastClosed: () =>
    set((s) => ({ visibleCount: Math.max(0, s.visibleCount - 1) })),
  setVisibleCount: (n) => set({ visibleCount: Math.max(0, n) }),
  setQueue: (queue) => set({ queue }),
  reset: () => set({ visibleCount: 0, queue: [] }),
}));
