"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { useSessionStore } from "@/stores/session-store";
import { useSetWebcamMode } from "@/hooks/use-onboarding";
import { useWebcamStore } from "@/stores/webcam-store";

export default function ProfilePage() {
  const { user } = useSessionStore();
  const setWebcam = useSetWebcamMode();
  const initWebcamMode = useWebcamStore((s) => s.initFromUser);
  const [msg, setMsg] = useState<{ type: "error" | "info"; text: string } | null>(null);

  if (!user) return null;

  const initials = `${user.firstName[0] ?? ""}${user.lastName[0] ?? ""}`.toUpperCase();
  const enabled = user.webcamEnabled ?? false;

  async function toggleWebcam() {
    if (setWebcam.isPending) return;
    const enabling = !enabled;
    setMsg(null);

    // Turning ON: re-request the browser camera permission first, so a learner who
    // previously denied it can grant it again at any time — no waiting period.
    if (enabling) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        stream.getTracks().forEach((t) => t.stop());
      } catch {
        setMsg({
          type: "error",
          text:
            "Your browser is blocking the camera. Click the camera / lock icon in the address bar " +
            "(or Site settings) to allow it for this site, then try again.",
        });
        return;
      }
    }

    try {
      await setWebcam.mutateAsync(enabling); // persists users.webcam_enabled + updates the session
      initWebcamMode(enabling); // flips the capture mode (adaptive / behavioral-only) immediately
      setMsg({
        type: "info",
        text: enabling
          ? "Webcam affect detection is ON. It will be used in your next learning session."
          : "Switched to behavioral-only mode — the camera is off.",
      });
    } catch {
      setMsg({ type: "error", text: "Could not save your preference. Please try again." });
    }
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Profile</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Your account details and learning preferences
        </p>
      </div>

      <div className="space-y-6">
        <div className="rounded-lg border border-border bg-surface p-6">
          <div className="flex items-center gap-4 mb-6">
            <span className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-2xl font-bold text-primary">
              {initials}
            </span>
            <div>
              <h2 className="text-lg font-semibold text-foreground">
                {user.firstName} {user.lastName}
              </h2>
              <p className="text-sm text-muted-foreground">{user.emailAddress}</p>
              <span className="mt-1 inline-flex items-center rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium capitalize text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                {user.role}
              </span>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {[
              { label: "First name", value: user.firstName },
              { label: "Last name", value: user.lastName },
              { label: "Email address", value: user.emailAddress },
              { label: "Adaptive mode", value: enabled ? "Webcam + Behavioral" : "Behavioral only" },
            ].map((field) => (
              <div key={field.label}>
                <p className="text-xs font-medium text-muted-foreground mb-1">{field.label}</p>
                <p className="text-sm text-foreground">{field.value}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-border bg-surface p-6">
          <h2 className="mb-1 font-semibold text-foreground">Privacy &amp; Webcam</h2>
          <p className="mb-4 text-sm text-muted-foreground">
            Control how AffectLearn uses your webcam for affect detection. You can turn this
            on or off at any time.
          </p>
          <div className="flex items-center justify-between py-2">
            <div>
              <p className="text-sm font-medium text-foreground">Webcam affect detection</p>
              <p className="text-xs text-muted-foreground">
                No video is stored — only facial feature vectors are sent to the server. With the
                camera off, AffectLearn adapts from behavioral signals only.
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={enabled}
              aria-label="Webcam affect detection"
              disabled={setWebcam.isPending}
              onClick={toggleWebcam}
              className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60 ${enabled ? "bg-primary" : "bg-border"}`}
            >
              <span
                className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${enabled ? "translate-x-5" : "translate-x-0.5"}`}
              />
            </button>
          </div>

          {setWebcam.isPending && (
            <p className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Saving preference…
            </p>
          )}
          {msg && (
            <div
              className={`mt-4 rounded-md border px-4 py-3 text-xs ${
                msg.type === "error"
                  ? "border-red-200 bg-red-50 text-red-700 dark:border-red-800/40 dark:bg-red-900/10 dark:text-red-400"
                  : "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800/40 dark:bg-blue-900/10 dark:text-blue-400"
              }`}
            >
              {msg.text}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
