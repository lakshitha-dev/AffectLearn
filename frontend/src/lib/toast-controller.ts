/**
 * Toast controller — the thin governor in front of `sonner` (Story 5.7).
 *
 * Story 5.7 is the toast layer for SYSTEM/operational messages only (`notification` +
 * `system.{mode_switch|error|reconnected}`). It is the LAST story of Epic 5 and completes
 * the per-notification-type routing matrix:
 *
 *   | message / action                                  | surface                 | story |
 *   |---------------------------------------------------|-------------------------|-------|
 *   | show_hint / show_alternative / show_breakdown     | inline callout          | 5.4   |
 *   | show_encouragement                                | subtle inline text      | 5.4   |
 *   | suggest_break                                     | overlay card (alertdlg) | 5.5   |
 *   | skip_ahead / increase_difficulty                  | skip/difficulty UI      | 5.6   |
 *   | notification + system.{mode_switch|error|reconnected} | TOAST (bottom-right) | 5.7   |
 *
 * Why this module exists (the load-bearing AC3): raw `sonner` stacks toasts unboundedly
 * and offers no 500ms inter-toast release delay. This controller sits in front of `toast.*`
 * and controls *when* each toast is actually shown, enforcing:
 *   - at most MAX_VISIBLE (2) toasts visible simultaneously;
 *   - additional toasts queued (FIFO) and released QUEUE_DELAY_MS (500ms) apart as slots free.
 * It does NOT replace `sonner` — `sonner` still owns rendering, the `aria-live` region, the
 * close button, richColors, and the per-toast auto-dismiss `duration`.
 *
 * Severity → `sonner` call / duration / a11y (the locked contract — AC2/AC5):
 *   - success → toast.success(msg, { duration: 3000 })   role="status" / polite, auto-dismiss 3s
 *   - info    → toast.info(msg,    { duration: 3000 })   role="status" / polite, auto-dismiss 3s
 *   - warning → toast.warning(msg, { duration: 3000 })   role="status" / polite, auto-dismiss 3s
 *   - error   → toast.error(msg,   { duration: Infinity }) role="alert" / assertive, persists
 *
 * Note on info: UX-1116 says 4s, the Epic-5 AC says 3s — the AC binds, so info uses 3000ms
 * (documented variance, Open Question #3).
 *
 * Async lives HERE, not in the store (`notification-store` is synchronous-setter plumbing).
 * The store remains the source of truth for `visibleCount` + `queue`; this controller drives
 * the release timer and the `sonner` calls and writes the resulting counts back to the store.
 */

import { toast } from "sonner";

import {
  useNotificationStore,
  MAX_VISIBLE,
  QUEUE_DELAY_MS,
  type ToastLevel,
  type ToastSpec,
} from "@/stores/notification-store";

const SUCCESS_DURATION_MS = 3000;

/** Stable id for a queued toast; falls back to a counter if crypto is unavailable.
 *  Mirrors the `_adaptationId` idiom in `use-websocket.ts`. */
let _toastSeq = 0;
export function makeToastId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  _toastSeq += 1;
  return `toast-${Date.now()}-${_toastSeq}`;
}

/**
 * Explicit severity → `sonner` mapping. Calling the right `toast.*` method is what gives the
 * correct a11y role/aria-live (sonner renders role="alert"/assertive for `error`,
 * role="status"/polite for the rest) AND the correct dismissal duration. `onClose` is wired
 * to BOTH `onAutoClose` and `onDismiss` so the governor frees a slot however the toast leaves.
 */
const LEVEL_TO_TOAST: Record<
  ToastLevel,
  (message: string, opts: { duration: number; onAutoClose: () => void; onDismiss: () => void }) => void
> = {
  success: (msg, opts) => toast.success(msg, opts),
  info: (msg, opts) => toast.info(msg, opts),
  warning: (msg, opts) => toast.warning(msg, opts),
  error: (msg, opts) => toast.error(msg, opts),
};

function durationFor(level: ToastLevel): number {
  // Errors persist until the learner dismisses them; everything else auto-dismisses at 3s.
  return level === "error" ? Infinity : SUCCESS_DURATION_MS;
}

// Async release bookkeeping lives in the module (not the store).
let releaseTimer: ReturnType<typeof setTimeout> | null = null;
let lastReleaseAt = 0;
// The 500ms spacing applies only AFTER the corner has filled to MAX_VISIBLE with toasts
// still queued (i.e. the initial fill to 2 is immediate — AC: "enqueue 3 → 2 released
// immediately"; the 3rd waits 500ms once a slot frees). This flag flips on once we saturate
// and resets when the queue fully drains.
let spacingActive = false;

/** Actually hand a spec to `sonner` and record it as visible. */
function show(spec: ToastSpec): void {
  const store = useNotificationStore.getState();
  store.setVisibleCount(store.visibleCount + 1);
  lastReleaseAt = Date.now();

  const onClose = () => {
    useNotificationStore.getState().onToastClosed();
    // A slot freed — try to drain the queue (respecting the 500ms spacing).
    drain();
  };

  LEVEL_TO_TOAST[spec.level](spec.message, {
    duration: durationFor(spec.level),
    onAutoClose: onClose,
    onDismiss: onClose,
  });
}

/**
 * Drain the queue: release as many queued toasts as the max-2 cap allows, but never closer
 * than QUEUE_DELAY_MS apart. If a release is due but too soon, schedule one timer for the
 * remaining wait and re-drain then. FIFO — the head of the queue is always released first.
 */
function drain(): void {
  const store = useNotificationStore.getState();

  if (store.queue.length === 0) {
    // Corner fully drained — the next burst gets a fresh immediate fill to the cap.
    spacingActive = false;
    return;
  }
  if (store.visibleCount >= MAX_VISIBLE) {
    // At the cap with items still queued — every subsequent release must be 500ms-spaced.
    spacingActive = true;
    return;
  }
  // A release is already scheduled — let it fire and re-drain; don't double-schedule.
  if (releaseTimer !== null) return;

  const elapsed = Date.now() - lastReleaseAt;
  if (spacingActive && elapsed < QUEUE_DELAY_MS) {
    // Post-saturation refill too soon since the last release — wait out the 500ms gap.
    releaseTimer = setTimeout(() => {
      releaseTimer = null;
      drain();
    }, QUEUE_DELAY_MS - elapsed);
    return;
  }

  const [head, ...rest] = store.queue;
  store.setQueue(rest);
  show(head);

  // More may be releasable now (up to the cap) — re-drain, which will space subsequent
  // releases 500ms apart via the timer branch above once we saturate.
  drain();
}

/**
 * Enqueue a system/notification toast. The controller decides whether to show it immediately
 * (slot free AND 500ms since the last release) or queue it for a spaced release. This is the
 * ONLY entry point `use-websocket.ts` calls — never raw `toast(...)` (which would bypass the
 * max-2 / 500ms governor — AC1/AC3).
 */
export function enqueueToast(spec: ToastSpec): void {
  useNotificationStore.getState().enqueue(spec);
  drain();
}

/**
 * Reset the controller — clears the pending release timer and zeroes the store counts.
 * Used by tests (between cases) and available for unmount cleanup so no late release fires.
 */
export function resetToastController(): void {
  if (releaseTimer !== null) {
    clearTimeout(releaseTimer);
    releaseTimer = null;
  }
  lastReleaseAt = 0;
  spacingActive = false;
  useNotificationStore.getState().reset();
}
