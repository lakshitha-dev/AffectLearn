"use client";

/**
 * Stub hook for behavioral signal collection.
 * Full implementation deferred to Epic 4 Story 4.3.
 * Interface is stable so lesson page can wire it without changes in Epic 4.
 */
export function useBehavioralSignals(active: boolean) {
  // Epic 4.3 will implement mouse/keyboard sampling at 10Hz
  // and WebSocket transmission of feature windows
  return { isActive: active };
}
