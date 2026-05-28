import { create } from "zustand";

export type WebcamMode = "adaptive" | "behavioral" | "error";

interface WebcamState {
  mode: WebcamMode;
  calibrated: boolean;
  setMode: (mode: WebcamMode) => void;
  setCalibrated: (v: boolean) => void;
  initFromUser: (webcamEnabled: boolean) => void;
}

export const useWebcamStore = create<WebcamState>()((set) => ({
  mode: "behavioral",
  calibrated: false,
  setMode: (mode) => set({ mode }),
  setCalibrated: (calibrated) => set({ calibrated }),
  initFromUser: (webcamEnabled) =>
    set({ mode: webcamEnabled ? "adaptive" : "behavioral" }),
}));