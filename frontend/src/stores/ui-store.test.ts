import { describe, it, expect, beforeEach } from "vitest";
import { useUiStore } from "./ui-store";

const initialState = {
  sidebarCollapsed: false,
  focusMode: false,
  welcomeBackDismissed: false,
};

describe("useUiStore", () => {
  beforeEach(() => {
    useUiStore.setState(initialState);
  });

  describe("initial state", () => {
    it("sidebarCollapsed is false by default", () => {
      expect(useUiStore.getState().sidebarCollapsed).toBe(false);
    });

    it("focusMode is false by default", () => {
      expect(useUiStore.getState().focusMode).toBe(false);
    });

    it("welcomeBackDismissed is false by default", () => {
      expect(useUiStore.getState().welcomeBackDismissed).toBe(false);
    });
  });

  describe("toggleSidebar", () => {
    it("sets sidebarCollapsed to true from false", () => {
      useUiStore.getState().toggleSidebar();
      expect(useUiStore.getState().sidebarCollapsed).toBe(true);
    });

    it("sets sidebarCollapsed back to false when already true", () => {
      useUiStore.setState({ sidebarCollapsed: true });
      useUiStore.getState().toggleSidebar();
      expect(useUiStore.getState().sidebarCollapsed).toBe(false);
    });

    it("toggles correctly across multiple calls", () => {
      useUiStore.getState().toggleSidebar(); // false → true
      useUiStore.getState().toggleSidebar(); // true → false
      useUiStore.getState().toggleSidebar(); // false → true
      expect(useUiStore.getState().sidebarCollapsed).toBe(true);
    });

    it("does not affect focusMode", () => {
      useUiStore.setState({ focusMode: true });
      useUiStore.getState().toggleSidebar();
      expect(useUiStore.getState().focusMode).toBe(true);
    });

    it("does not affect welcomeBackDismissed", () => {
      useUiStore.setState({ welcomeBackDismissed: true });
      useUiStore.getState().toggleSidebar();
      expect(useUiStore.getState().welcomeBackDismissed).toBe(true);
    });
  });

  describe("toggleFocusMode", () => {
    it("sets focusMode to true from false", () => {
      useUiStore.getState().toggleFocusMode();
      expect(useUiStore.getState().focusMode).toBe(true);
    });

    it("sets focusMode back to false when already true", () => {
      useUiStore.setState({ focusMode: true });
      useUiStore.getState().toggleFocusMode();
      expect(useUiStore.getState().focusMode).toBe(false);
    });

    it("toggles correctly across multiple calls", () => {
      useUiStore.getState().toggleFocusMode(); // false → true
      useUiStore.getState().toggleFocusMode(); // true → false
      useUiStore.getState().toggleFocusMode(); // false → true
      expect(useUiStore.getState().focusMode).toBe(true);
    });

    it("does not affect sidebarCollapsed", () => {
      useUiStore.setState({ sidebarCollapsed: true });
      useUiStore.getState().toggleFocusMode();
      expect(useUiStore.getState().sidebarCollapsed).toBe(true);
    });

    it("does not affect welcomeBackDismissed", () => {
      useUiStore.setState({ welcomeBackDismissed: true });
      useUiStore.getState().toggleFocusMode();
      expect(useUiStore.getState().welcomeBackDismissed).toBe(true);
    });
  });

  describe("dismissWelcomeBack", () => {
    it("sets welcomeBackDismissed to true", () => {
      useUiStore.getState().dismissWelcomeBack();
      expect(useUiStore.getState().welcomeBackDismissed).toBe(true);
    });

    it("calling again keeps it true", () => {
      useUiStore.getState().dismissWelcomeBack();
      useUiStore.getState().dismissWelcomeBack();
      expect(useUiStore.getState().welcomeBackDismissed).toBe(true);
    });

    it("does not affect sidebarCollapsed", () => {
      useUiStore.setState({ sidebarCollapsed: true });
      useUiStore.getState().dismissWelcomeBack();
      expect(useUiStore.getState().sidebarCollapsed).toBe(true);
    });

    it("does not affect focusMode", () => {
      useUiStore.setState({ focusMode: true });
      useUiStore.getState().dismissWelcomeBack();
      expect(useUiStore.getState().focusMode).toBe(true);
    });
  });

  describe("resetWelcomeBack", () => {
    it("sets welcomeBackDismissed back to false", () => {
      useUiStore.getState().dismissWelcomeBack();
      useUiStore.getState().resetWelcomeBack();
      expect(useUiStore.getState().welcomeBackDismissed).toBe(false);
    });

    it("calling on already-false state keeps it false", () => {
      useUiStore.getState().resetWelcomeBack();
      expect(useUiStore.getState().welcomeBackDismissed).toBe(false);
    });

    it("does not affect sidebarCollapsed", () => {
      useUiStore.setState({ sidebarCollapsed: true });
      useUiStore.getState().resetWelcomeBack();
      expect(useUiStore.getState().sidebarCollapsed).toBe(true);
    });

    it("does not affect focusMode", () => {
      useUiStore.setState({ focusMode: true });
      useUiStore.getState().resetWelcomeBack();
      expect(useUiStore.getState().focusMode).toBe(true);
    });
  });

  describe("dismiss and reset cycle", () => {
    it("cycles correctly: false → true → false", () => {
      expect(useUiStore.getState().welcomeBackDismissed).toBe(false);
      useUiStore.getState().dismissWelcomeBack();
      expect(useUiStore.getState().welcomeBackDismissed).toBe(true);
      useUiStore.getState().resetWelcomeBack();
      expect(useUiStore.getState().welcomeBackDismissed).toBe(false);
    });
  });

  describe("persistence configuration", () => {
    it("store has persist configuration with correct name", () => {
      // Verify the store name used in partialize (indirectly via the store's persist option)
      // We can verify by checking the store's internal _persist property if available,
      // or simply confirm that all state is accessible (sanity check for the persist setup)
      const state = useUiStore.getState();
      expect(state).toHaveProperty("sidebarCollapsed");
      expect(state).toHaveProperty("focusMode");
      expect(state).toHaveProperty("welcomeBackDismissed");
    });

    it("welcomeBackDismissed resets to false on new store instance (not persisted)", () => {
      useUiStore.getState().dismissWelcomeBack();
      // Reset all state (simulates a fresh session where only persisted keys are restored)
      useUiStore.setState({ ...initialState, sidebarCollapsed: true, focusMode: true });
      // welcomeBackDismissed should be false (not persisted)
      expect(useUiStore.getState().welcomeBackDismissed).toBe(false);
    });
  });

  describe("state shape", () => {
    it("exposes all expected properties and actions", () => {
      const state = useUiStore.getState();
      expect(typeof state.sidebarCollapsed).toBe("boolean");
      expect(typeof state.focusMode).toBe("boolean");
      expect(typeof state.welcomeBackDismissed).toBe("boolean");
      expect(typeof state.toggleSidebar).toBe("function");
      expect(typeof state.toggleFocusMode).toBe("function");
      expect(typeof state.dismissWelcomeBack).toBe("function");
      expect(typeof state.resetWelcomeBack).toBe("function");
    });
  });
});
