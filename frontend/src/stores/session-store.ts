import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { UserResponse } from "@/types/api-responses";

interface SessionState {
  accessToken: string | null;
  refreshToken: string | null;
  expiresAt: number | null;
  user: UserResponse | null;
  setTokens: (accessToken: string, refreshToken: string, expiresIn: number) => void;
  setUser: (user: UserResponse | null) => void;
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

      setTokens: (accessToken, refreshToken, expiresIn) =>
        set({
          accessToken,
          refreshToken,
          expiresAt: Date.now() + expiresIn * 1000,
        }),

      setUser: (user) => set({ user }),

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
    },
  ),
);
