"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useChangePassword } from "@/hooks/use-profile";
import { ApiRequestError } from "@/lib/api-client";

/**
 * Change your own password.
 *
 * `POST /auth/change-password` has existed since the auth epic, fully implemented and tested, and
 * nothing in any role's interface ever called it. A signed-in user's only route to a new password
 * was to sign out and use the "forgot password" email flow, which is a strange thing to ask of
 * someone who knows their current password and is already authenticated.
 *
 * The current password is required by the endpoint even though the caller holds a valid token —
 * a token left behind on a shared machine should not be enough to lock the owner out.
 */

// Same policy as registration and reset, kept identical so a password accepted in one place is
// not rejected in another. The server enforces it independently; this is only the early message.
const passwordPolicy = z
  .string()
  .min(8, "Password must be at least 8 characters")
  .regex(/[a-z]/, "Must contain a lowercase letter")
  .regex(/[A-Z]/, "Must contain an uppercase letter")
  .regex(/\d/, "Must contain a digit")
  .regex(/[!@#$%^&*()_+\-=\[\]{};':"\|,.<>\/?]/, "Must contain a special character");

const schema = z
  .object({
    currentPassword: z.string().min(1, "Enter your current password"),
    newPassword: passwordPolicy,
    confirmPassword: z.string(),
  })
  .refine((d) => d.newPassword === d.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  })
  .refine((d) => d.newPassword !== d.currentPassword, {
    message: "Choose a password different from your current one",
    path: ["newPassword"],
  });

type PasswordData = z.infer<typeof schema>;

export function ChangePasswordForm() {
  const changePassword = useChangePassword();
  const [serverError, setServerError] = useState<string | null>(null);

  const form = useForm<PasswordData>({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: { currentPassword: "", newPassword: "", confirmPassword: "" },
  });

  const onSubmit = async (data: PasswordData) => {
    setServerError(null);
    try {
      await changePassword.mutateAsync({
        currentPassword: data.currentPassword,
        newPassword: data.newPassword,
      });
      toast.success("Password changed. We've emailed you a confirmation.");
      form.reset();
    } catch (err) {
      // The endpoint distinguishes a wrong current password from everything else, and so should
      // the message — "something went wrong" would send someone to the reset flow needlessly.
      if (err instanceof ApiRequestError && err.errorCode === "INVALID_CREDENTIALS") {
        form.setError("currentPassword", { message: "That is not your current password" });
      } else {
        setServerError("Could not change your password. Please try again.");
      }
    }
  };

  return (
    <section className="rounded-lg border border-border bg-surface p-6">
      <h2 className="font-semibold text-foreground">Password</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Changing your password signs out any outstanding reset links.
      </p>

      <form
        onSubmit={form.handleSubmit(onSubmit)}
        noValidate
        className="mt-5 max-w-md space-y-4"
      >
        {serverError && (
          <div
            className="rounded-md border border-error/30 bg-error/5 p-3 text-sm text-error"
            role="alert"
          >
            {serverError}
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="currentPassword">Current password</Label>
          <Input
            id="currentPassword"
            type="password"
            autoComplete="current-password"
            className={`h-10 ${form.formState.errors.currentPassword ? "border-error" : ""}`}
            {...form.register("currentPassword")}
          />
          {form.formState.errors.currentPassword && (
            <p className="text-sm text-error">
              {form.formState.errors.currentPassword.message}
            </p>
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="newPassword">New password</Label>
          <Input
            id="newPassword"
            type="password"
            autoComplete="new-password"
            className={`h-10 ${form.formState.errors.newPassword ? "border-error" : ""}`}
            {...form.register("newPassword")}
          />
          {form.formState.errors.newPassword && (
            <p className="text-sm text-error">{form.formState.errors.newPassword.message}</p>
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="confirmPassword">Confirm new password</Label>
          <Input
            id="confirmPassword"
            type="password"
            autoComplete="new-password"
            className={`h-10 ${form.formState.errors.confirmPassword ? "border-error" : ""}`}
            {...form.register("confirmPassword")}
          />
          {form.formState.errors.confirmPassword && (
            <p className="text-sm text-error">
              {form.formState.errors.confirmPassword.message}
            </p>
          )}
        </div>

        <div className="flex justify-end">
          <Button type="submit" disabled={changePassword.isPending}>
            {changePassword.isPending ? "Changing…" : "Change password"}
          </Button>
        </div>
      </form>
    </section>
  );
}
