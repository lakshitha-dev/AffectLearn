"use client";

import { useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StepIndicator } from "./StepIndicator";
import { useWebcamStore } from "@/stores/webcam-store";

type CalibrationState = "counting" | "success" | "failure";

interface CalibrationStepProps {
  onDone: () => void;
  onSkip: () => void;
  currentStep: number;
  totalSteps: number;
}

export function CalibrationStep({ onDone, onSkip, currentStep, totalSteps }: CalibrationStepProps) {
  const [countdown, setCountdown] = useState(10);
  const [state, setState] = useState<CalibrationState>("counting");
  const { setCalibrated } = useWebcamStore();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function startCountdown() {
    if (intervalRef.current) clearInterval(intervalRef.current);
    setCountdown(10);
    setState("counting");
    let remaining = 10;
    intervalRef.current = setInterval(() => {
      remaining -= 1;
      setCountdown(remaining);
      if (remaining <= 0) {
        clearInterval(intervalRef.current!);
        intervalRef.current = null;
        // Simulate face detection success (real MediaPipe integration in Epic 4)
        setState("success");
        setCalibrated(true);
      }
    }, 1000);
  }

  useEffect(() => {
    startCountdown();
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const progress = ((10 - countdown) / 10) * 100;
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
            We couldn&apos;t detect your face clearly. Check lighting and camera angle, or skip to continue
            with behavioral monitoring.
          </p>
          <div className="flex gap-3 justify-center">
            <Button variant="outline" onClick={startCountdown}>
              Try again
            </Button>
            <Button variant="outline" onClick={onSkip}>Skip</Button>
          </div>
        </div>
      )}

      {state === "counting" && (
        <p className="text-sm text-muted-foreground">Look at the screen normally…</p>
      )}
    </div>
  );
}