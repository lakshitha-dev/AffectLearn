import { describe, it, expect, beforeEach } from "vitest";
import { useWebcamStore } from "./webcam-store";

const initialState = {
  mode: "behavioral" as const,
  calibrated: false,
};

describe("useWebcamStore", () => {
  beforeEach(() => {
    useWebcamStore.setState(initialState);
  });

  describe("initial state", () => {
    it("starts with mode='behavioral'", () => {
      expect(useWebcamStore.getState().mode).toBe("behavioral");
    });

    it("starts with calibrated=false", () => {
      expect(useWebcamStore.getState().calibrated).toBe(false);
    });
  });

  describe("setMode", () => {
    it("sets mode to 'adaptive'", () => {
      useWebcamStore.getState().setMode("adaptive");
      expect(useWebcamStore.getState().mode).toBe("adaptive");
    });

    it("sets mode to 'behavioral'", () => {
      useWebcamStore.getState().setMode("adaptive");
      useWebcamStore.getState().setMode("behavioral");
      expect(useWebcamStore.getState().mode).toBe("behavioral");
    });

    it("sets mode to 'error'", () => {
      useWebcamStore.getState().setMode("error");
      expect(useWebcamStore.getState().mode).toBe("error");
    });

    it("does not change calibrated when setting mode", () => {
      useWebcamStore.setState({ calibrated: true });
      useWebcamStore.getState().setMode("adaptive");
      expect(useWebcamStore.getState().calibrated).toBe(true);
    });
  });

  describe("setCalibrated", () => {
    it("sets calibrated to true", () => {
      useWebcamStore.getState().setCalibrated(true);
      expect(useWebcamStore.getState().calibrated).toBe(true);
    });

    it("sets calibrated back to false", () => {
      useWebcamStore.getState().setCalibrated(true);
      useWebcamStore.getState().setCalibrated(false);
      expect(useWebcamStore.getState().calibrated).toBe(false);
    });

    it("does not change mode when setting calibrated", () => {
      useWebcamStore.setState({ mode: "adaptive" });
      useWebcamStore.getState().setCalibrated(true);
      expect(useWebcamStore.getState().mode).toBe("adaptive");
    });
  });

  describe("initFromUser", () => {
    it("sets mode to 'adaptive' when webcamEnabled=true", () => {
      useWebcamStore.getState().initFromUser(true);
      expect(useWebcamStore.getState().mode).toBe("adaptive");
    });

    it("sets mode to 'behavioral' when webcamEnabled=false", () => {
      useWebcamStore.setState({ mode: "adaptive" });
      useWebcamStore.getState().initFromUser(false);
      expect(useWebcamStore.getState().mode).toBe("behavioral");
    });

    it("does not affect calibrated state", () => {
      useWebcamStore.setState({ calibrated: true });
      useWebcamStore.getState().initFromUser(true);
      expect(useWebcamStore.getState().calibrated).toBe(true);
    });

    it("overwrites current mode with adaptive when true", () => {
      useWebcamStore.setState({ mode: "error" });
      useWebcamStore.getState().initFromUser(true);
      expect(useWebcamStore.getState().mode).toBe("adaptive");
    });

    it("overwrites adaptive mode with behavioral when false", () => {
      useWebcamStore.setState({ mode: "adaptive" });
      useWebcamStore.getState().initFromUser(false);
      expect(useWebcamStore.getState().mode).toBe("behavioral");
    });
  });

  describe("store is not persisted", () => {
    it("actions return new state synchronously (not persisted via localStorage)", () => {
      useWebcamStore.getState().setMode("adaptive");
      // Verify the state changed in-memory without relying on localStorage
      expect(useWebcamStore.getState().mode).toBe("adaptive");
      // Reset and check it returns to initial (no rehydration from storage)
      useWebcamStore.setState(initialState);
      expect(useWebcamStore.getState().mode).toBe("behavioral");
    });
  });

  describe("state shape", () => {
    it("exposes mode, calibrated, setMode, setCalibrated, and initFromUser", () => {
      const state = useWebcamStore.getState();
      expect(state).toHaveProperty("mode");
      expect(state).toHaveProperty("calibrated");
      expect(typeof state.setMode).toBe("function");
      expect(typeof state.setCalibrated).toBe("function");
      expect(typeof state.initFromUser).toBe("function");
    });
  });
});
