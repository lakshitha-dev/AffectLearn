"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { WelcomeStep } from "@/components/onboarding/WelcomeStep";
import { ConsentStep } from "@/components/onboarding/ConsentStep";
import { WebcamStep } from "@/components/onboarding/WebcamStep";
import { CalibrationStep } from "@/components/onboarding/CalibrationStep";
import { useGiveConsent, useSetWebcamMode } from "@/hooks/use-onboarding";
import { useSessionStore } from "@/stores/session-store";
import { useWebcamStore } from "@/stores/webcam-store";
import { AuthGuard } from "@/components/shared/auth-guard";

type OnboardingStep = "welcome" | "consent" | "webcam" | "calibration";

const TOTAL_STEPS = 4;
const STEP_NUMBERS: Record<OnboardingStep, number> = {
  welcome: 1, consent: 2, webcam: 3, calibration: 4,
};

export default function OnboardingPage() {
  const router = useRouter();
  const user = useSessionStore((s) => s.user);
  const { mode, setMode } = useWebcamStore();
  const [step, setStep] = useState<OnboardingStep>("welcome");

  const consentMutation = useGiveConsent();
  const webcamModeMutation = useSetWebcamMode();

  // Only redirect if user arrived at /onboarding already consented (not after giving consent mid-wizard)
  const initialConsentRef = useRef(user?.consentGivenAt);
  useEffect(() => {
    if (initialConsentRef.current) {
      router.replace("/courses");
    }
  }, [router]);

  async function handleConsentAgree() {
    try {
      await consentMutation.mutateAsync(undefined);
      setStep("webcam");
    } catch {
      toast.error("Could not save consent. Please try again.");
    }
  }

  async function handleWebcamDecision(enabled: boolean) {
    setMode(enabled ? "adaptive" : "behavioral");
    try {
      await webcamModeMutation.mutateAsync(enabled);
    } catch {
      // Non-critical — proceed anyway
    }
    if (enabled) {
      setStep("calibration");
    } else {
      router.replace("/courses");
    }
  }

  function handleCalibrationDone() {
    router.replace("/courses");
  }

  const currentStepNum = STEP_NUMBERS[step];

  return (
    <AuthGuard allowedRoles={["learner"]}>
      <div className="min-h-screen flex items-center justify-center bg-background px-4 py-16">
        <div className="w-full max-w-2xl">
          {step === "welcome" && (
            <WelcomeStep
              firstName={user?.firstName ?? null}
              onNext={() => setStep("consent")}
              currentStep={currentStepNum}
              totalSteps={TOTAL_STEPS}
            />
          )}
          {step === "consent" && (
            <ConsentStep
              onAgree={handleConsentAgree}
              onBack={() => setStep("welcome")}
              isSubmitting={consentMutation.isPending}
              currentStep={currentStepNum}
              totalSteps={TOTAL_STEPS}
            />
          )}
          {step === "webcam" && (
            <WebcamStep
              onDecision={handleWebcamDecision}
              currentStep={currentStepNum}
              totalSteps={TOTAL_STEPS}
            />
          )}
          {step === "calibration" && (
            <CalibrationStep
              onDone={handleCalibrationDone}
              onSkip={() => { setMode("behavioral"); router.replace("/courses"); }}
              currentStep={currentStepNum}
              totalSteps={TOTAL_STEPS}
            />
          )}
        </div>
      </div>
    </AuthGuard>
  );
}