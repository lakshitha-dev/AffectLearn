"use client";

import { useSessionStore } from "@/stores/session-store";

export default function ProfilePage() {
  const { user } = useSessionStore();

  if (!user) return null;

  const initials = `${user.firstName[0] ?? ""}${user.lastName[0] ?? ""}`.toUpperCase();

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
              { label: "Adaptive mode", value: user.webcamEnabled ? "Webcam + Behavioral" : "Behavioral only" },
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
            Control how AffectLearn uses your webcam for affect detection
          </p>
          <div className="flex items-center justify-between py-2">
            <div>
              <p className="text-sm font-medium text-foreground">Webcam affect detection</p>
              <p className="text-xs text-muted-foreground">
                No video is stored — only facial feature vectors are sent to the server
              </p>
            </div>
            <div
              className={`h-5 w-9 rounded-full ${user.webcamEnabled ? "bg-primary" : "bg-border"} cursor-not-allowed opacity-70`}
              role="switch"
              aria-checked={user.webcamEnabled ?? false}
              aria-label="Webcam affect detection"
            />
          </div>
          <div className="mt-4 flex items-center gap-2 rounded-md border border-blue-200 bg-blue-50 dark:border-blue-800/40 dark:bg-blue-900/10 px-4 py-3">
            <svg className="h-4 w-4 text-blue-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-xs text-blue-700 dark:text-blue-400">
              Webcam preference can be updated from the learning session settings. Data is retained
              for 90 days after study completion.
            </p>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            disabled
            className="rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground opacity-50 cursor-not-allowed"
          >
            Save changes
          </button>
        </div>
      </div>
    </div>
  );
}
