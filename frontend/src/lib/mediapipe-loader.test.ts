import { describe, it, expect, beforeEach, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const createFromOptionsSpy = vi.fn();
  const forVisionTasksSpy = vi.fn();
  const closeSpy = vi.fn();

  return {
    createFromOptionsSpy,
    forVisionTasksSpy,
    closeSpy,
  };
});

vi.mock("@mediapipe/tasks-vision", () => ({
  FaceDetector: {
    createFromOptions: mocks.createFromOptionsSpy,
  },
  FilesetResolver: {
    forVisionTasks: mocks.forVisionTasksSpy,
  },
}));

import {
  loadFaceDetector,
  disposeFaceDetector,
  __resetForTests,
} from "./mediapipe-loader";

describe("mediapipe-loader", () => {
  beforeEach(() => {
    __resetForTests();
    mocks.createFromOptionsSpy.mockReset();
    mocks.forVisionTasksSpy.mockReset();
    mocks.closeSpy.mockReset();

    mocks.forVisionTasksSpy.mockResolvedValue({ wasm: "fileset" });
  });

  it("requests GPU delegate first and resolves a detector", async () => {
    const fakeDetector = { close: mocks.closeSpy };
    mocks.createFromOptionsSpy.mockResolvedValueOnce(fakeDetector);

    const detector = await loadFaceDetector();

    expect(detector).toBe(fakeDetector);
    expect(mocks.forVisionTasksSpy).toHaveBeenCalledTimes(1);
    expect(mocks.createFromOptionsSpy).toHaveBeenCalledTimes(1);
    const opts = mocks.createFromOptionsSpy.mock.calls[0][1];
    expect(opts.baseOptions.delegate).toBe("GPU");
    expect(opts.baseOptions.modelAssetPath).toMatch(/blaze_face_short_range/);
    expect(opts.runningMode).toBe("VIDEO");
    expect(opts.minDetectionConfidence).toBe(0.5);
  });

  it("falls back to CPU delegate when GPU initialization fails", async () => {
    const cpuDetector = { close: mocks.closeSpy };
    mocks.createFromOptionsSpy
      .mockRejectedValueOnce(new Error("WebGL2 not available"))
      .mockResolvedValueOnce(cpuDetector);

    const detector = await loadFaceDetector();

    expect(detector).toBe(cpuDetector);
    expect(mocks.createFromOptionsSpy).toHaveBeenCalledTimes(2);
    expect(mocks.createFromOptionsSpy.mock.calls[0][1].baseOptions.delegate).toBe("GPU");
    expect(mocks.createFromOptionsSpy.mock.calls[1][1].baseOptions.delegate).toBe("CPU");
  });

  it("caches the detector — concurrent calls share one creation", async () => {
    const fakeDetector = { close: mocks.closeSpy };
    mocks.createFromOptionsSpy.mockResolvedValue(fakeDetector);

    const [a, b, c] = await Promise.all([
      loadFaceDetector(),
      loadFaceDetector(),
      loadFaceDetector(),
    ]);

    expect(a).toBe(fakeDetector);
    expect(b).toBe(fakeDetector);
    expect(c).toBe(fakeDetector);
    expect(mocks.createFromOptionsSpy).toHaveBeenCalledTimes(1);
    expect(mocks.forVisionTasksSpy).toHaveBeenCalledTimes(1);
  });

  it("disposeFaceDetector closes the detector and clears the cache", async () => {
    const fakeDetector = { close: mocks.closeSpy };
    mocks.createFromOptionsSpy.mockResolvedValue(fakeDetector);

    await loadFaceDetector();
    await disposeFaceDetector();

    expect(mocks.closeSpy).toHaveBeenCalledTimes(1);

    // After dispose, a new load triggers a fresh create.
    await loadFaceDetector();
    expect(mocks.createFromOptionsSpy).toHaveBeenCalledTimes(2);
  });

  it("disposeFaceDetector is a no-op if nothing was loaded", async () => {
    await expect(disposeFaceDetector()).resolves.toBeUndefined();
    expect(mocks.closeSpy).not.toHaveBeenCalled();
  });

  it("clears the cache if both GPU and CPU fail, so a retry is possible", async () => {
    mocks.createFromOptionsSpy
      .mockRejectedValueOnce(new Error("GPU fail"))
      .mockRejectedValueOnce(new Error("CPU fail"));

    await expect(loadFaceDetector()).rejects.toThrow("CPU fail");

    // After the failure, a fresh attempt should restart from scratch.
    const recoveryDetector = { close: mocks.closeSpy };
    mocks.createFromOptionsSpy.mockResolvedValueOnce(recoveryDetector);
    const result = await loadFaceDetector();
    expect(result).toBe(recoveryDetector);
  });
});
