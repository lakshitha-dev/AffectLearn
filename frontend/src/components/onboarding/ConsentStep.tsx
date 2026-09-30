"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { StepIndicator } from "./StepIndicator";
import type { ConsentScopes } from "@/types/api-responses";

interface ConsentStepProps {
  onAgree: (scopes: ConsentScopes) => void;
  onBack: () => void;
  isSubmitting: boolean;
  currentStep: number;
  totalSteps: number;
}

// Everything below is a privacy CLAIM made before consent, so it must describe what the code
// does. The version is `CONSENT_VERSION` in `lib/consent.ts`; change the text, bump the version.
// Retention periods and the withdrawal deadline are set by the study protocol and stated in the
// participant information sheet, so they are referred to rather than restated here.
export function ConsentStep({ onAgree, onBack, isSubmitting, currentStep, totalSteps }: ConsentStepProps) {
  const [checked, setChecked] = useState(false);
  const [rawInteraction, setRawInteraction] = useState(false);

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <StepIndicator currentStep={currentStep} totalSteps={totalSteps} />

      <div>
        <h1 className="text-2xl font-semibold text-foreground">Research Study Consent</h1>
        <p className="mt-1 text-sm text-muted-foreground">Please read the following carefully before participating.</p>
      </div>

      <div className="rounded-xl border border-border bg-surface p-6 space-y-5 text-sm text-foreground leading-relaxed max-h-80 overflow-y-auto">
        <section>
          <h2 className="font-semibold">Webcam Facial Analysis (optional)</h2>
          <p className="mt-1 text-muted-foreground">
            If you allow the camera on the next screen, your camera images are analysed on your own device and{" "}
            <strong>no photographs or video ever leave your computer or are stored</strong>. What is sent to the
            server, once a second, is a short list of measurements taken from each image — where your eyes are
            looking, how open your eyes and mouth are, the angle of your head, and how much you are moving. These
            measurements cannot be turned back into a picture of your face. The system uses them to estimate
            whether you seem engaged. That estimate is a guess by a computer model and is often wrong. You can
            say no to the camera and still take part.
          </p>
        </section>
        <section>
          <h2 className="font-semibold">Mouse, Scroll &amp; Keyboard Activity</h2>
          <p className="mt-1 text-muted-foreground">
            While you are on a lesson page, the app records where the mouse pointer is (about ten times a second
            while it moves), clicks and what was clicked, scrolling, whether the tab is visible, and the{" "}
            <em>kind</em> of each key you press (letter, digit, space, backspace, and so on) with its timing.{" "}
            <strong>It never records which key you pressed or anything you type</strong>, and it never records
            passwords. Every 30 seconds this activity is turned into summary measurements used to estimate
            whether you seem confused.
          </p>
        </section>
        <section>
          <h2 className="font-semibold">Answers, Progress &amp; Your Feedback</h2>
          <p className="mt-1 text-muted-foreground">
            The study also records your quiz and test answers, which sections you open and for how long, any help
            the system offers and what you do with it, and your answers to the short questions about how you
            feel and about the system.
          </p>
        </section>
        <section>
          <h2 className="font-semibold">Help Messages and Outside Services</h2>
          <p className="mt-1 text-muted-foreground">
            Some participants receive help messages written by an AI model. To write them, the text of the section
            you are on, a description of your estimated state (for example “seems disengaged”) and your recent
            activity in that section (for example how many answers were wrong) are sent to OpenAI. Your name,
            email address and account are never sent. Video suggestions come from YouTube, and the face-analysis
            software is downloaded from Google and jsDelivr servers; none of them receives camera images.
          </p>
        </section>
        <section>
          <h2 className="font-semibold">Data Usage &amp; Storage</h2>
          <p className="mt-1 text-muted-foreground">
            Your data is used only for this research study. Research records are{" "}
            <strong>pseudonymised</strong>: they are linked to a study account and code, not to your name. The
            researcher keeps the link between your name and your code separately and destroys it after the
            withdrawal deadline. Access is limited to the researcher and their supervisor. How long each kind of
            data is kept is stated in the participant information sheet.
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
          <h2 className="font-semibold">Right to Stop and to Withdraw</h2>
          <p className="mt-1 text-muted-foreground">
            You may stop at any time without giving a reason and without any consequence: tell the researcher, or
            use “Stop taking part” on your profile page, and all recording stops straight away. You can also ask
            for everything recorded about you to be deleted, up to the withdrawal deadline in the information
            sheet; deleting your account from the profile page does this immediately.
          </p>
        </section>
      </div>

      <label className="flex items-start gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={rawInteraction}
          onChange={(e) => setRawInteraction(e.target.checked)}
          className="mt-0.5 h-4 w-4 rounded border-border accent-primary"
        />
        <span className="text-sm text-foreground">
          <strong>Optional:</strong> also keep the detailed activity record (pointer positions, clicks, scrolls
          and key kinds with their timing) for later research analysis, not just the 30-second summaries. You
          can take part without this.
        </span>
      </label>

      <label className="flex items-start gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => setChecked(e.target.checked)}
          className="mt-0.5 h-4 w-4 rounded border-border accent-primary"
        />
        <span className="text-sm text-foreground">
          I have read and understood the above consent information and agree to take part
        </span>
      </label>

      <div className="flex gap-3">
        <Button variant="outline" onClick={onBack}>Back</Button>
        <Button
          disabled={!checked || isSubmitting}
          aria-disabled={!checked || isSubmitting}
          title={!checked ? "Please tick the checkbox to continue" : undefined}
          onClick={() => onAgree({ behavioural: true, rawInteraction })}
        >
          {isSubmitting ? "Saving…" : "I agree"}
        </Button>
      </div>
    </div>
  );
}
