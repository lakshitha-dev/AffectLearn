import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";

const mocks = vi.hoisted(() => ({
  loadFaceDetectorSpy: vi.fn(),
  detectForVideoSpy: vi.fn(),
}));

vi.mock("@/lib/mediapipe-loader", () => ({
  loadFaceDetector: mocks.loadFaceDetectorSpy,
}));

import { CalibrationStep } from "./CalibrationStep";
import { useWebcamStore } from "@/stores/webcam-store";

describe("CalibrationStep — MediaPipe integration (Story 4.2 AC #6)", () => {
  let getUserMediaMock: ReturnType<typeof vi.fn>;
  let originalDescriptor: PropertyDescriptor | undefined;

  function makeDetector(scoresOverTime: number[]) {
    let i = 0;
    mocks.detectForVideoSpy.mockImplementation(() => {
      const score = i < scoresOverTime.length ? scoresOverTime[i] : 0;
      i += 1;
      return score === 0
        ? { detections: [] }
        : {
            detections: [
              {
                categories: [{ score }],
                boundingBox: {
                  originX: 0,
                  originY: 0,
                  width: 100,
                  height: 100,
                },
              },
            ],
          };
    });
    return {
      detectForVideo: mocks.detectForVideoSpy,
      close: vi.fn(),
    };
  }

  beforeEach(() => {
    vi.useFakeTimers();

    mocks.loadFaceDetectorSpy.mockReset();
    mocks.detectForVideoSpy.mockReset();

    const stream = {
      getTracks: () => [
        {
          stop: vi.fn(),
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        },
      ],
    };
    getUserMediaMock = vi.fn().mockResolvedValue(stream);

    originalDescriptor = Object.getOwnPropertyDescriptor(
      navigator,
      "mediaDevices",
    );
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: getUserMediaMock },
    });

    Object.defineProperty(HTMLMediaElement.prototype, "play", {
      configurable: true,
      value: vi.fn().mockResolvedValue(undefined),
    });
    Object.defineProperty(HTMLMediaElement.prototype, "readyState", {
      configurable: true,
      get: () => 4,
    });

    useWebcamStore.setState({ mode: "adaptive", calibrated: false });
  });

  afterEach(() => {
    vi.useRealTimers();
    if (originalDescriptor) {
      Object.defineProperty(navigator, "mediaDevices", originalDescriptor);
    }
  });

  it("succeeds when ≥ 7 of 10 frames score ≥ 0.7 and mean confidence ≥ 0.5", async () => {
    mocks.loadFaceDetectorSpy.mockResolvedValueOnce(
      makeDetector([0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9]),
    );

    render(
      <CalibrationStep
        onDone={vi.fn()}
        onSkip={vi.fn()}
        currentStep={3}
        totalSteps={3}
      />,
    );

    // Wait for getUserMedia + detector load.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });

    // 10 capture ticks.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(useWebcamStore.getState().calibrated).toBe(true);
    expect(screen.getByText(/All set/i)).toBeInTheDocument();
  });

  it("fails when fewer than 7 frames score ≥ 0.7", async () => {
    // Only 5 frames pass the 0.7 bar.
    mocks.loadFaceDetectorSpy.mockResolvedValueOnce(
      makeDetector([0.9, 0.9, 0.9, 0.9, 0.9, 0.3, 0.3, 0.3, 0.3, 0.3]),
    );

    render(
      <CalibrationStep
        onDone={vi.fn()}
        onSkip={vi.fn()}
        currentStep={3}
        totalSteps={3}
      />,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(useWebcamStore.getState().calibrated).toBe(false);
    expect(screen.getByText(/Try again/i)).toBeInTheDocument();
  });

  it("fails when no face is ever detected", async () => {
    mocks.loadFaceDetectorSpy.mockResolvedValueOnce(
      makeDetector([0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
    );

    render(
      <CalibrationStep
        onDone={vi.fn()}
        onSkip={vi.fn()}
        currentStep={3}
        totalSteps={3}
      />,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(useWebcamStore.getState().calibrated).toBe(false);
    expect(screen.getByText(/Try again/i)).toBeInTheDocument();
  });

  it("fails when getUserMedia is denied", async () => {
    getUserMediaMock.mockRejectedValueOnce(new Error("NotAllowedError"));

    render(
      <CalibrationStep
        onDone={vi.fn()}
        onSkip={vi.fn()}
        currentStep={3}
        totalSteps={3}
      />,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });

    expect(screen.getByText(/Try again/i)).toBeInTheDocument();
    expect(useWebcamStore.getState().calibrated).toBe(false);
  });

  it("preserves Skip path → invokes onSkip when user clicks Skip after failure", async () => {
    mocks.loadFaceDetectorSpy.mockResolvedValueOnce(
      makeDetector([0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
    );
    const onSkip = vi.fn();

    render(
      <CalibrationStep
        onDone={vi.fn()}
        onSkip={onSkip}
        currentStep={3}
        totalSteps={3}
      />,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    const skipButton = screen.getByText(/^Skip$/);
    act(() => skipButton.click());
    expect(onSkip).toHaveBeenCalled();
  });
});
