"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StepIndicator } from "./StepIndicator";

type WebcamState = "idle" | "active" | "denied";

interface WebcamStepProps {
  onDecision: (enabled: boolean) => void;
  currentStep: number;
  totalSteps: number;
}

// These four lines are a privacy CLAIM shown before consent, so they must describe what the code
// does rather than what it was intended to do. Images are analysed on-device and only derived
// measurements are transmitted -- see `lib/geometry.ts` and `hooks/use-media-pipe.ts`, which send
// `geometry` and no longer send any frame data.
const PRIVACY_ITEMS = [
  "Your camera images are analysed on your device",
  "No photos or video are ever sent or stored",
  "Only measurements are sent — eye, mouth and head position",
  "You can turn this off anytime in settings",
  "All data deleted within 90 days after study",
];

export function WebcamStep({ onDecision, currentStep, totalSteps }: WebcamStepProps) {
  const [webcamState, setWebcamState] = useState<WebcamState>("idle");
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // Stop stream on unmount to turn off the webcam LED
  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  // Attach the stream once the <video> is mounted (it only renders when active).
  useEffect(() => {
    if (webcamState === "active" && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
    }
  }, [webcamState]);

  const requestWebcam = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      streamRef.current = stream;
      setWebcamState("active");
    } catch {
      setWebcamState("denied");
      setTimeout(() => onDecision(false), 3000);
    }
  }, [onDecision]);

  function handleSkip() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
    }
    onDecision(false);
  }

  function handleContinueWithWebcam() {
    onDecision(true);
  }

  return (
    <div className="space-y-6 max-w-md mx-auto">
      <StepIndicator currentStep={currentStep} totalSteps={totalSteps} />

      <div>
        <h1 className="text-2xl font-semibold text-foreground">Webcam access</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Enable your webcam to allow the system to detect your emotional state while learning.
        </p>
      </div>

      {/* Camera preview */}
      <div className="relative aspect-video rounded-xl border border-border bg-surface overflow-hidden">
        {webcamState === "active" ? (
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            className="absolute inset-0 w-full h-full object-cover"
          />
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground text-sm text-center space-y-2 p-6">
            <div className="w-12 h-12 rounded-full bg-border flex items-center justify-center text-2xl">
              📷
            </div>
            <p>Camera preview will appear here</p>
          </div>
        )}
      </div>

      {/* Privacy checklist */}
      <ul className="space-y-2">
        {PRIVACY_ITEMS.map((item) => (
          <li key={item} className="flex items-start gap-2 text-sm text-muted-foreground">
            <Check className="h-4 w-4 mt-0.5 text-success shrink-0" />
            {item}
          </li>
        ))}
      </ul>

      {webcamState === "denied" && (
        <p className="text-sm text-muted-foreground bg-surface rounded-lg p-3">
          No problem — behavioral mode works great too. Redirecting you…
        </p>
      )}

      <div className="flex gap-3">
        {webcamState === "idle" && (
          <>
            <Button onClick={requestWebcam}>Enable webcam</Button>
            <Button variant="outline" onClick={handleSkip}>Skip for now</Button>
          </>
        )}
        {webcamState === "active" && (
          <Button onClick={handleContinueWithWebcam}>Continue</Button>
        )}
      </div>
    </div>
  );
}