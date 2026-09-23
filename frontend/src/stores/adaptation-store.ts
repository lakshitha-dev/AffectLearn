/**
 * Adaptation store — ephemeral client-side queue of delivered adaptations (Story 5.3).
 *
 * The backend pushes an `adaptation` WS message at the end of a Phase B cycle; the
 * `useWebSocket` hook parses it and calls `pushAdaptation` to append it here. This store
 * is PLUMBING ONLY: it accumulates the queue and nothing renders it yet. Stories 5.4–5.7
 * (inline hint callout, break card, skip/difficulty UI, notification toasts) consume this
 * queue and `dismissAdaptation(id)` an item once shown/acted on.
 *
 * Pattern (architecture lines 600-617, enforced): a FLAT store with SYNCHRONOUS setters
 * only — async lives in hooks, never in stores. Mirrors `connection-store.ts` /
 * `webcam-store.ts`. NOT persisted (the queue is fully ephemeral, like connection state).
 *
 * Architecture line 803 imagined a single `session-store.ts` owning the adaptation queue,
 * but Story 4.1 already split connection state into its own store (session-store holds JWT
 * auth). We continue that per-concern decomposition with a dedicated `adaptation-store`.
 */

import { create } from "zustand";

import type { AdaptationAction } from "@/types/ws-messages";

export interface AdaptationVideo {
  kind?: "embed" | "link";
  url?: string;
  videoId?: string;
  title?: string;
  channel?: string;
  durationS?: number;
  reason?: string;
  /** The sub-agent ran out of time in the cycle; finish the lookup with this brief. */
  pending?: boolean;
  concept?: string;
  query?: string;
}

export interface Adaptation {
  /** Stable client-generated id so 5.4–5.6 can key/dismiss (crypto.randomUUID). */
  id: string;
  action: AdaptationAction;
  text?: string;
  variant?: string;
  /** `show_video` only: the Video sub-agent's result, camelCased from the wire. */
  video?: AdaptationVideo;
  /** Client receipt time (ms) for ordering / staleness in later stories. */
  receivedAt: number;
}

interface AdaptationState {
  adaptationQueue: Adaptation[];
  pushAdaptation: (a: Adaptation) => void;
  dismissAdaptation: (id: string) => void;
  reset: () => void;
}

const initialState = {
  adaptationQueue: [] as Adaptation[],
};

export const useAdaptationStore = create<AdaptationState>()((set) => ({
  ...initialState,
  pushAdaptation: (a) =>
    set((s) => ({ adaptationQueue: [...s.adaptationQueue, a] })),
  dismissAdaptation: (id) =>
    set((s) => ({ adaptationQueue: s.adaptationQueue.filter((x) => x.id !== id) })),
  reset: () => set({ adaptationQueue: [] }),
}));
