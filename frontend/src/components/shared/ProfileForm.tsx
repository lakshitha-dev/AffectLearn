"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useUpdateProfile } from "@/hooks/use-profile";
import { useSessionStore } from "@/stores/session-store";

/**
 * Edit your own name, age range and degree programme.
 *
 * Shared by every role rather than written per area: the designer settings page previously showed
 * an invented name and department behind disabled inputs, and the learner profile page rendered
 * the real values as read-only text with no way to correct a typo made at registration. Both
 * needed the same form, so there is one.
 *
 * Email and role are shown but not editable — email is the login identifier and would need the
 * same verification round-trip registration uses, and role is an administrative decision.
 */

// Mirrors the options offered at registration, so a value chosen here is one the study's
// demographics can actually group by.
const AGE_RANGES = ["18-24", "25-34", "35-44", "45-54", "55+"] as const;

const schema = z.object({
  firstName: z.string().min(1, "First name is required").max(100),
  lastName: z.string().min(1, "Last name is required").max(100),
  ageRange: z.string().max(20).optional(),
  degreeProgram: z.string().max(200).optional(),
});

type ProfileData = z.infer<typeof schema>;

export function ProfileForm() {
  const user = useSessionStore((s) => s.user);
  const updateProfile = useUpdateProfile();
  const [serverError, setServerError] = useState<string | null>(null);

  const form = useForm<ProfileData>({
    resolver: zodResolver(schema),
    mode: "onBlur",
    values: {
      firstName: user?.firstName ?? "",
      lastName: user?.lastName ?? "",
      ageRange: user?.ageRange ?? "",
      degreeProgram: user?.degreeProgram ?? "",
    },
  });

  if (!user) return null;

  const onSubmit = async (data: ProfileData) => {
    setServerError(null);
    try {
      await updateProfile.mutateAsync({
        firstName: data.firstName,
        lastName: data.lastName,
        // Empty select/input means "no answer", which the column stores as NULL.
        ageRange: data.ageRange ? data.ageRange : null,
        degreeProgram: data.degreeProgram ? data.degreeProgram : null,
      });
      toast.success("Profile updated");
      form.reset(data);
    } catch {
      setServerError("Could not save your profile. Please try again.");
    }
  };

  return (
    <section className="rounded-lg border border-border bg-surface p-6">
      <h2 className="font-semibold text-foreground">Profile</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Your name as it appears across AffectLearn.
      </p>

      <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="mt-5 space-y-4">
        {serverError && (
          <div
            className="rounded-md border border-error/30 bg-error/5 p-3 text-sm text-error"
            role="alert"
          >
            {serverError}
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="firstName">First name</Label>
            <Input
              id="firstName"
              className={`h-10 ${form.formState.errors.firstName ? "border-error" : ""}`}
              {...form.register("firstName")}
            />
            {form.formState.errors.firstName && (
              <p className="text-sm text-error">{form.formState.errors.firstName.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="lastName">Last name</Label>
            <Input
              id="lastName"
              className={`h-10 ${form.formState.errors.lastName ? "border-error" : ""}`}
              {...form.register("lastName")}
            />
            {form.formState.errors.lastName && (
              <p className="text-sm text-error">{form.formState.errors.lastName.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="ageRange">Age range</Label>
            <select
              id="ageRange"
              className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              {...form.register("ageRange")}
            >
              <option value="">Prefer not to say</option>
              {AGE_RANGES.map((range) => (
                <option key={range} value={range}>
                  {range}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="degreeProgram">Degree programme</Label>
            <Input id="degreeProgram" className="h-10" {...form.register("degreeProgram")} />
          </div>
        </div>

        {/* Shown, not editable — see the component docstring for why each is fixed here. */}
        <div className="grid gap-4 border-t border-border pt-4 sm:grid-cols-2">
          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">Email address</p>
            <p className="text-sm text-foreground">{user.emailAddress}</p>
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">Role</p>
            <p className="text-sm capitalize text-foreground">
              {user.role.replace("_", " ")}
            </p>
          </div>
        </div>

        <div className="flex justify-end">
          <Button type="submit" disabled={updateProfile.isPending || !form.formState.isDirty}>
            {updateProfile.isPending ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </form>
    </section>
  );
}
