"use client";

import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { PasswordInput } from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";

const schema = z.object({
  password: z
    .string()
    .min(8, "Password must be at least 8 characters")
    .regex(/[a-z]/, "Must contain a lowercase letter")
    .regex(/[A-Z]/, "Must contain an uppercase letter")
    .regex(/\d/, "Must contain a digit")
    .regex(/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/, "Must contain a special character"),
});

type FormData = z.infer<typeof schema>;

function ResetPasswordInner() {
  const params = useSearchParams();
  const router = useRouter();
  const { resetPassword } = useAuth();
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const token = params.get("token");

  const form = useForm<FormData>({
    resolver: zodResolver(schema),
    mode: "onBlur",
  });

  const onSubmit = async (data: FormData) => {
    if (!token) {
      setServerError("This reset link is missing its token.");
      return;
    }
    setIsSubmitting(true);
    setServerError(null);
    try {
      await resetPassword(token, data.password);
      setDone(true);
      setTimeout(() => router.push("/login"), 1500);
    } catch (err) {
      if (
        err instanceof ApiRequestError &&
        (err.errorCode === "TOKEN_EXPIRED" || err.errorCode === "TOKEN_USED" || err.errorCode === "INVALID_TOKEN")
      ) {
        setServerError("This reset link is invalid or has expired. Please request a new one.");
      } else {
        setServerError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (done) {
    return (
      <Card className="rounded-none border-border shadow-sm">
        <CardHeader>
          <CardTitle className="text-2xl tracking-tight">Password updated</CardTitle>
          <CardDescription>Your password has been reset — taking you to sign in.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className="rounded-none border-border shadow-sm">
      <CardHeader>
        <CardTitle className="text-2xl tracking-tight">Choose a new password</CardTitle>
        <CardDescription>Enter a new password for your account.</CardDescription>
      </CardHeader>

      <CardContent>
        <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-4">
          {serverError && (
            <div
              className="rounded-md border border-error/30 bg-error/5 p-3 text-sm text-error"
              role="alert"
              aria-live="polite"
            >
              {serverError}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="password">
              New password <span className="text-muted-foreground">*</span>
            </Label>
            <PasswordInput
              id="password"
              autoComplete="new-password"
              className={`h-11 ${form.formState.errors.password ? "border-error" : ""}`}
              {...form.register("password")}
            />
            {form.formState.errors.password && (
              <p className="text-sm text-error" role="alert">
                {form.formState.errors.password.message}
              </p>
            )}
          </div>

          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Updating..." : "Update password"}
          </Button>
        </form>
      </CardContent>

      <CardFooter className="justify-center">
        <Link href="/login" className="text-sm font-medium text-primary hover:underline">
          Back to sign in
        </Link>
      </CardFooter>
    </Card>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordInner />
    </Suspense>
  );
}
