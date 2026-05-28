import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UiState {
  sidebarCollapsed: boolean;
  focusMode: boolean;
  welcomeBackDismissed: boolean;
  toggleSidebar: () => void;
  toggleFocusMode: () => void;
  dismissWelcomeBack: () => void;
  resetWelcomeBack: () => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      focusMode: false,
      welcomeBackDismissed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      toggleFocusMode: () => set((s) => ({ focusMode: !s.focusMode })),
      dismissWelcomeBack: () => set({ welcomeBackDismissed: true }),
      resetWelcomeBack: () => set({ welcomeBackDismissed: false }),
    }),
    {
      name: "affectlearn-ui",
      // Only persist sidebar/focus preferences; welcomeBackDismissed is session-only
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        focusMode: state.focusMode,
      }),
    }
  )
);
