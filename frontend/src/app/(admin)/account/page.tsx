"use client";

import { ChangePasswordForm } from "@/components/shared/ChangePasswordForm";
import { ProfileForm } from "@/components/shared/ProfileForm";

/**
 * The admin's OWN account.
 *
 * Kept separate from `/admin-settings`, which configures the adaptation gate for the whole
 * deployment. Those are different things with different blast radii, and putting "change my
 * password" on the same screen as "change the confidence floor for every learner" invites the
 * wrong click.
 *
 * Before this, an admin had no way to change their own password from inside the product at all —
 * the endpoint existed, and every role's UI ignored it.
 */
export default function AdminAccountPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Account</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Your own profile and password. System configuration lives under Settings.
        </p>
      </div>

      <div className="max-w-3xl space-y-6">
        <ProfileForm />
        <ChangePasswordForm />
      </div>
    </div>
  );
}
