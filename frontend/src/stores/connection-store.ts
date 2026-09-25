/**
 * Connection store — ephemeral state for the learner WebSocket session.
 *
 * Story 4.1 Deviation 1: The architecture spec (line 803) names `session-store.ts` for
 * "Affect state, adaptation queue, connection", but `session-store.ts` already holds
 * JWT auth state (Story 1.2). To avoid a cross-cutting rename that would churn
 * `api-client.ts`, `use-auth.ts`, and others, we put connection state in a separate
 * dedicated store, matching the team's existing per-concern decomposition pattern
 * (webcam-store, ui-store, session-store).
 *
 * This store is NOT persisted — connection state is fully ephemeral.
 */

import { create } from "zustand";

export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "open"
  | "reconnecting"
  | "closed"
  | "auth_failed";

interface ConnectionState {
  isConnected: boolean;
  connectionState: ConnectionStatus;
  lastError: string | null;
  reconnectAttempts: number;
  sessionRestored: boolean;
  /** Whether this learner receives adaptations; null until the server says. */
  adaptive: boolean | null;
  setAdaptive: (adaptive: boolean | null) => void;
  setConnected: (connected: boolean) => void;
  setConnectionState: (state: ConnectionStatus) => void;
  setError: (msg: string | null) => void;
  incrementReconnect: () => void;
  resetReconnect: () => void;
  markSessionRestored: () => void;
  reset: () => void;
}

const initialState = {
  isConnected: false,
  connectionState: "idle" as ConnectionStatus,
  lastError: null,
  reconnectAttempts: 0,
  sessionRestored: false,
  adaptive: null as boolean | null,
};

export const useConnectionStore = create<ConnectionState>()((set) => ({
  ...initialState,
  setConnected: (connected) => set({ isConnected: connected }),
  setConnectionState: (state) => set({ connectionState: state }),
  setError: (msg) => set({ lastError: msg }),
  incrementReconnect: () =>
    set((s) => ({ reconnectAttempts: s.reconnectAttempts + 1 })),
  resetReconnect: () => set({ reconnectAttempts: 0 }),
  markSessionRestored: () => set({ sessionRestored: true }),
  setAdaptive: (adaptive) => set({ adaptive }),
  reset: () => set(initialState),
}));
