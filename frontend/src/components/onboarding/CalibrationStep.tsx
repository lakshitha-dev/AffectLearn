"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StepIndicator } from "./StepIndicator";
import { useWebcamStore } from "@/stores/webcam-store";
import { loadFaceDetector } from "@/lib/mediapipe-loader";

type CalibrationState = "counting" | "success" | "failure";

interface CalibrationStepProps {
  onDone: () => void;
  onSkip: () => void;
  currentStep: number;
  totalSteps: number;
}

// Story 4.2 AC #6 — pass requires ≥ 7 of 10 frames at score ≥ 0.7 AND mean confidence ≥ 0.7.
// Mean threshold aligned to Success Criteria (story section "Success Criteria", mean ≥ 0.7).
const PASS_FRAME_COUNT = 7;
const PASS_FRAME_SCORE = 0.7;
const PASS_MEAN_CONFIDENCE = 0.7;
const CALIBRATION_DURATION_SECONDS = 10;

export function CalibrationStep({ onDone, onSkip, currentStep, totalSteps }: CalibrationStepProps) {
  const [countdown, setCountdown] = useState(CALIBRATION_DURATION_SECONDS);
  const [state, setState] = useState<CalibrationState>("counting");
  const { setCalibrated } = useWebcamStore();

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  // Refs (not state) for per-tick counters — countdown ticks fire faster than React can flush.
  const successfulFramesRef = useRef(0);
  const sumScoresRef = useRef(0);
  const scoredFramesRef = useRef(0);

  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
      videoRef.current = null;
    }
  }, []);

  const startCountdown = useCallback(async () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    stopStream();
    successfulFramesRef.current = 0;
    sumScoresRef.current = 0;
    scoredFramesRef.current = 0;
    setCountdown(CALIBRATION_DURATION_SECONDS);
    setState("counting");

    // Re-acquire the stream — Story 4.2 Q4: re-acquire on entry (~200ms flash, clean teardown).
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: true });
    } catch (err) {
      console.warn("[CalibrationStep] getUserMedia failed", err);
      setState("failure");
      return;
    }
    streamRef.current = stream;

    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    video.srcObject = stream;
    videoRef.current = video;
    try {
      await video.play();
    } catch (err) {
      console.warn("[CalibrationStep] video.play() rejected", err);
    }

    let detector;
    try {
      detector = await loadFaceDetector();
    } catch (err) {
      console.warn("[CalibrationStep] face detector load failed", err);
      stopStream();
      setState("failure");
      return;
    }

    // If the component unmounted while we were awaiting, bail.
    if (!streamRef.current) return;

    let remaining = CALIBRATION_DURATION_SECONDS;
    intervalRef.current = setInterval(() => {
      // Run one MediaPipe detection per tick.
      if (videoRef.current && videoRef.current.readyState >= 2) {
        try {
          const result = detector.detectForVideo(
            videoRef.current,
            performance.now(),
          );
          const score = result?.detections?.[0]?.categories?.[0]?.score ?? 0;
          if (score > 0) {
            sumScoresRef.current += score;
            scoredFramesRef.current += 1;
          }
          if (score >= PASS_FRAME_SCORE) {
            successfulFramesRef.current += 1;
          }
        } catch (err) {
          console.warn("[CalibrationStep] detectForVideo threw", err);
        }
      }

      remaining -= 1;
      setCountdown(remaining);
      if (remaining <= 0) {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }

        const meanConfidence =
          scoredFramesRef.current > 0
            ? sumScoresRef.current / scoredFramesRef.current
            : 0;
        const passed =
          successfulFramesRef.current >= PASS_FRAME_COUNT &&
          meanConfidence >= PASS_MEAN_CONFIDENCE;

        // Architectural privacy guarantee: no calibration data is persisted server-side.
        // The pass/fail is purely a client-side gate.
        stopStream();

        if (passed) {
          setCalibrated(true);
          setState("success");
        } else {
          setState("failure");
        }
      }
    }, 1000);
  }, [setCalibrated, stopStream]);

  useEffect(() => {
    void startCountdown();
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      stopStream();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const progress = ((CALIBRATION_DURATION_SECONDS - countdown) / CALIBRATION_DURATION_SECONDS) * 100;
  const circumference = 2 * Math.PI * 44;

  return (
    <div className="space-y-8 max-w-sm mx-auto text-center">
      <StepIndicator currentStep={currentStep} totalSteps={totalSteps} />

      <div>
        <h1 className="text-2xl font-semibold text-foreground">Webcam calibration</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Look at your screen normally for 10 seconds while we establish your baseline.
        </p>
      </div>

      {/* Circular progress ring */}
      <div className="flex items-center justify-center">
        <div className="relative w-28 h-28">
          <svg className="w-28 h-28 -rotate-90" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="44" fill="none" stroke="currentColor" strokeWidth="8" className="text-border" />
            <circle
              cx="50" cy="50" r="44" fill="none"
              stroke="currentColor" strokeWidth="8"
              strokeDasharray={circumference}
              strokeDashoffset={circumference - (circumference * progress) / 100}
              strokeLinecap="round"
              className={state === "success" ? "text-success" : "text-primary"}
              style={{ transition: "stroke-dashoffset 0.5s ease" }}
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            {state === "success" ? (
              <Check className="h-8 w-8 text-success" />
            ) : (
              <span className="text-2xl font-bold text-foreground">{countdown}</span>
            )}
          </div>
        </div>
      </div>

      {state === "success" && (
        <div className="space-y-4">
          <p className="text-success font-medium">All set!</p>
          <Button onClick={onDone}>Continue to courses</Button>
        </div>
      )}

      {state === "failure" && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            No problem — the camera didn&apos;t get a clear read, so we&apos;ll use your
            behavioral signals (mouse, typing, scrolling) instead. You can continue now, or try
            the camera again.
          </p>
          <div className="flex gap-3 justify-center">
            <Button onClick={onSkip}>Continue</Button>
            <Button variant="outline" onClick={() => void startCountdown()}>
              Try camera again
            </Button>
          </div>
        </div>
      )}

      {state === "counting" && (
        <p className="text-sm text-muted-foreground">Look at the screen normally…</p>
      )}
    </div>
  );
}
