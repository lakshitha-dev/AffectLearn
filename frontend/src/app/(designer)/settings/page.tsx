"use client";

import { ChangePasswordForm } from "@/components/shared/ChangePasswordForm";
import { ProfileForm } from "@/components/shared/ProfileForm";

/**
 * Designer settings.
 *
 * This page used to be entirely invented: a hardcoded "Dr. Morgan / morgan@university.edu /
 * Computer Science" behind four disabled inputs, three notification toggles that were `div`s
 * rather than controls, and a Save button that was permanently disabled. Nothing on it read or
 * wrote anything, and the name it displayed belonged to no account.
 *
 * It now shows the signed-in designer's real profile and lets them change their own password —
 * `POST /auth/change-password` was implemented the whole time and no screen in any role called it.
 *
 * The notification toggles are GONE rather than wired up. There is no notification system behind
 * them, no preferences table, and no requirement in the PRD asking for one; building a scheduler
 * and an email digest to justify three checkboxes that were only ever decoration would be
 * inventing scope. Removing them is the honest fix — the same call the admin pages made when
 * their fabricated panels were replaced with real data.
 */
export default function DesignerSettingsPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Your account details and password
        </p>
      </div>

      <div className="max-w-3xl space-y-6">
        <ProfileForm />
        <ChangePasswordForm />
      </div>
    </div>
  );
}
