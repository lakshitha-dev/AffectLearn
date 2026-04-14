import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UiState {
  sidebarCollapsed: boolean;
  focusMode: boolean;
  toggleSidebar: () => void;
  toggleFocusMode: () => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      focusMode: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      toggleFocusMode: () => set((s) => ({ focusMode: !s.focusMode })),
    }),
    { name: "affectlearn-ui" }
  )
);
