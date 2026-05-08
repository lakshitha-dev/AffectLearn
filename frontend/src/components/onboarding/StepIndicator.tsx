import { cn } from "@/lib/cn";

interface StepIndicatorProps {
  currentStep: number;
  totalSteps: number;
}

export function StepIndicator({ currentStep, totalSteps }: StepIndicatorProps) {
  return (
    <div className="flex items-center gap-2" aria-label={`Step ${currentStep} of ${totalSteps}`}>
      {Array.from({ length: totalSteps }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "h-2 w-2 rounded-full transition-colors",
            i + 1 === currentStep ? "bg-primary" : i + 1 < currentStep ? "bg-primary/40" : "bg-border"
          )}
        />
      ))}
    </div>
  );
}