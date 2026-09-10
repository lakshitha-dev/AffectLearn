"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { StepIndicator } from "./StepIndicator";

interface ConsentStepProps {
  onAgree: () => void;
  onBack: () => void;
  isSubmitting: boolean;
  currentStep: number;
  totalSteps: number;
}

export function ConsentStep({ onAgree, onBack, isSubmitting, currentStep, totalSteps }: ConsentStepProps) {
  const [checked, setChecked] = useState(false);

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <StepIndicator currentStep={currentStep} totalSteps={totalSteps} />

      <div>
        <h1 className="text-2xl font-semibold text-foreground">Research Study Consent</h1>
        <p className="mt-1 text-sm text-muted-foreground">Please read the following carefully before participating.</p>
      </div>

      <div className="rounded-xl border border-border bg-surface p-6 space-y-5 text-sm text-foreground leading-relaxed max-h-80 overflow-y-auto">
        <section>
          <h2 className="font-semibold">Webcam Facial Analysis</h2>
          <p className="mt-1 text-muted-foreground">
            With your permission, the system uses your webcam to help detect when you seem disengaged while
            learning. Your camera images are analysed on your own device and{" "}
            <strong>no photographs or video ever leave your computer</strong>. What is sent to the server is a
            short list of measurements taken from each image — where your eyes are looking, how open your mouth
            is, the position of your head, and how much you are moving. These measurements cannot be turned back
            into a picture of your face.
          </p>
        </section>
        <section>
          <h2 className="font-semibold">Mouse &amp; Keyboard Behavioural Tracking</h2>
          <p className="mt-1 text-muted-foreground">
            The system collects mouse movement, scroll, and keyboard activity patterns in 30-second windows to
            supplement affect detection. Raw keystrokes are never recorded — only aggregate features (entropy, frequency).
          </p>
        </section>
        <section>
          <h2 className="font-semibold">Data Usage &amp; Storage</h2>
          <p className="mt-1 text-muted-foreground">
            Your data is used solely for this research study. All records are anonymised using random session tokens —
            no personally identifiable information is stored in the research dataset. Data is retained for a maximum
            of 90 days after the study ends, after which it is automatically deleted.
          </p>
        </section>
        <section>
          <h2 className="font-semibold">What to Expect from the Material</h2>
          <p className="mt-1 text-muted-foreground">
            The course is an ordinary set of lessons on AI agents. Some parts may feel clear and
            engaging, some may feel slow or tedious, and a few may feel challenging or confusing —
            this range is a normal part of learning and is exactly what this study looks at. There
            is no minimum score, and nothing here is a test of you. You can pause, skip a
            self-report prompt, or stop at any time.
          </p>
        </section>
        <section>
          <h2 className="font-semibold">Right to Withdraw</h2>
          <p className="mt-1 text-muted-foreground">
            You may withdraw from this study at any time without consequence. Upon withdrawal, all your data will be
            permanently deleted within 24 hours.
          </p>
        </section>
      </div>

      <label className="flex items-start gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => setChecked(e.target.checked)}
          className="mt-0.5 h-4 w-4 rounded border-border accent-primary"
        />
        <span className="text-sm text-foreground">
          I have read and understood the above consent information
        </span>
      </label>

      <div className="flex gap-3">
        <Button variant="outline" onClick={onBack}>Back</Button>
        <Button
          disabled={!checked || isSubmitting}
          aria-disabled={!checked || isSubmitting}
          title={!checked ? "Please tick the checkbox to continue" : undefined}
          onClick={onAgree}
        >
          {isSubmitting ? "Saving…" : "I agree"}
        </Button>
      </div>
    </div>
  );
}