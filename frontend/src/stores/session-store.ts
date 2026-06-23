import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { UserResponse } from "@/types/api-responses";

interface SessionState {
  accessToken: string | null;
  refreshToken: string | null;
  expiresAt: number | null;
  user: UserResponse | null;
  // True once the persisted session has been read back from localStorage. Guards must
  // wait for this before deciding to redirect — otherwise they redirect on the initial
  // (pre-hydration) null state and bounce between /login and the dashboard.
  hasHydrated: boolean;
  setTokens: (accessToken: string, refreshToken: string, expiresIn: number) => void;
  setUser: (user: UserResponse | null) => void;
  setHasHydrated: (v: boolean) => void;
  clearSession: () => void;
  isAuthenticated: () => boolean;
  shouldRefresh: () => boolean;
}

export const useSessionStore = create<SessionState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      expiresAt: null,
      user: null,
      hasHydrated: false,

      setTokens: (accessToken, refreshToken, expiresIn) =>
        set({
          accessToken,
          refreshToken,
          expiresAt: Date.now() + expiresIn * 1000,
        }),

      setUser: (user) => set({ user }),

      setHasHydrated: (v) => set({ hasHydrated: v }),

      clearSession: () =>
        set({
          accessToken: null,
          refreshToken: null,
          expiresAt: null,
          user: null,
        }),

      isAuthenticated: () => {
        const { accessToken, expiresAt } = get();
        return accessToken !== null && expiresAt !== null && Date.now() < expiresAt;
      },

      shouldRefresh: () => {
        const { expiresAt, refreshToken } = get();
        if (!expiresAt || !refreshToken) return false;
        // Refresh 5 minutes before expiry
        return Date.now() > expiresAt - 5 * 60 * 1000;
      },
    }),
    {
      name: "affectlearn-session",
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        expiresAt: state.expiresAt,
        user: state.user,
      }),
      // Fires after the persisted state is read back; flips hasHydrated so guards can
      // safely evaluate auth. Runs even when there's nothing stored.
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    },
  ),
);
