import { Button } from "@/components/ui/button";
import { StepIndicator } from "./StepIndicator";

interface WelcomeStepProps {
  firstName: string | null;
  onNext: () => void;
  currentStep: number;
  totalSteps: number;
}

export function WelcomeStep({ firstName, onNext, currentStep, totalSteps }: WelcomeStepProps) {
  const heading = firstName
    ? `Welcome, ${firstName}! Let's set up your learning experience.`
    : "Welcome! Let's set up your learning experience.";

  return (
    <div className="space-y-8 text-center max-w-lg mx-auto">
      <StepIndicator currentStep={currentStep} totalSteps={totalSteps} />
      <div className="space-y-4">
        <h1 className="text-3xl font-semibold text-foreground">{heading}</h1>
        <p className="text-base text-muted-foreground">
          Before you start learning, we need to set up a few things to personalise your experience
          and explain how your data is used in this research study.
        </p>
      </div>
      <Button size="lg" onClick={onNext}>Get started</Button>
    </div>
  );
}