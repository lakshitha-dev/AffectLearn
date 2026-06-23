"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

const loginSchema = z.object({
  emailAddress: z.string().email("Please enter a valid email address"),
  password: z.string().min(1, "Password is required"),
});

type LoginData = z.infer<typeof loginSchema>;

const ROLE_REDIRECTS: Record<string, string> = {
  learner: "/courses",
  course_designer: "/analytics",
  admin: "/users",
};

const ROLE_LABELS: Record<string, string> = {
  learner: "Learner",
  course_designer: "Course Designer",
  admin: "Platform Admin",
};

const ROLE_ROUTES: Record<string, string> = {
  learner: "/onboarding → /courses",
  course_designer: "/analytics (Designer Dashboard)",
  admin: "/users (Admin Console)",
};

interface DevAccount {
  role: string;
  email_address: string;
  password: string;
  first_name: string;
  last_name: string;
}

interface DevCredentialsResponse {
  environment: string;
  accounts: DevAccount[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export default function LoginPage() {
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [devCreds, setDevCreds] = useState<DevCredentialsResponse | null>(null);
  const [needsVerification, setNeedsVerification] = useState(false);
  const [resendNotice, setResendNotice] = useState<string | null>(null);
  const { login, resendVerification } = useAuth();
  const router = useRouter();

  const form = useForm<LoginData>({
    resolver: zodResolver(loginSchema),
    mode: "onBlur",
  });

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/auth/dev-credentials`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: DevCredentialsResponse | null) => {
        if (!cancelled && data) setDevCreds(data);
      })
      .catch(() => {
        /* silent — dev credentials are optional */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const onValidationError = (errors: Record<string, unknown>) => {
    const firstKey = Object.keys(errors)[0] as keyof LoginData;
    if (firstKey) form.setFocus(firstKey);
  };

  const onSubmit = async (data: LoginData) => {
    setIsSubmitting(true);
    setServerError(null);
    setNeedsVerification(false);
    setResendNotice(null);

    try {
      const user = await login(data);
      const needsOnboarding =
        user.role === "learner" && !user.consentGivenAt;
      const redirect = needsOnboarding
        ? "/onboarding"
        : (ROLE_REDIRECTS[user.role] ?? "/courses");
      router.push(redirect);
    } catch (err) {
      if (err instanceof ApiRequestError && err.errorCode === "INVALID_CREDENTIALS") {
        setServerError("Invalid email or password. Please try again.");
      } else if (err instanceof ApiRequestError && err.errorCode === "EMAIL_NOT_VERIFIED") {
        setNeedsVerification(true);
      } else {
        setServerError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const onResend = async () => {
    const email = form.getValues("emailAddress");
    if (!email) return;
    try {
      await resendVerification(email);
    } finally {
      // Generic confirmation regardless of outcome (no account enumeration).
      setResendNotice("If that account needs verifying, we've sent a fresh link.");
    }
  };

  const useAccount = (acct: DevAccount) => {
    form.setValue("emailAddress", acct.email_address, { shouldValidate: true });
    form.setValue("password", acct.password, { shouldValidate: true });
    setServerError(null);
  };

  const fillAndSubmit = async (acct: DevAccount) => {
    useAccount(acct);
    await onSubmit({ emailAddress: acct.email_address, password: acct.password });
  };

  return (
    <Card className="rounded-none border-border shadow-sm">
      <CardHeader>
        <CardTitle className="text-2xl tracking-tight">Welcome back</CardTitle>
        <CardDescription>
          Sign in to continue adapting to how you learn.
        </CardDescription>
      </CardHeader>

      <CardContent>
        <form
          onSubmit={form.handleSubmit(onSubmit, onValidationError)}
          noValidate
          className="space-y-4"
        >
          {serverError && (
            <div
              className="rounded-md border border-error/30 bg-error/5 p-3 text-sm text-error"
              role="alert"
              aria-live="polite"
            >
              {serverError}
            </div>
          )}

          {needsVerification && (
            <div
              className="rounded-md border border-warning/30 bg-warning/5 p-3 text-sm text-foreground"
              role="alert"
              aria-live="polite"
            >
              <p>Please verify your email before signing in.</p>
              {resendNotice ? (
                <p className="mt-2 text-muted-foreground">{resendNotice}</p>
              ) : (
                <button
                  type="button"
                  onClick={onResend}
                  className="mt-2 font-medium text-primary hover:underline"
                >
                  Resend verification email
                </button>
              )}
            </div>
          )}

          <fieldset className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="emailAddress">
                Email <span className="text-muted-foreground">*</span>
              </Label>
              <Input
                id="emailAddress"
                type="email"
                autoComplete="email"
                className={`h-11 ${form.formState.errors.emailAddress ? "border-error" : ""}`}
                {...form.register("emailAddress")}
              />
              {form.formState.errors.emailAddress && (
                <p className="text-sm text-error" role="alert">
                  {form.formState.errors.emailAddress.message}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">
                  Password <span className="text-muted-foreground">*</span>
                </Label>
                <Link
                  href="/forgot-password"
                  className="text-sm font-medium text-primary hover:underline"
                >
                  Forgot password?
                </Link>
              </div>
              <PasswordInput
                id="password"
                autoComplete="current-password"
                className={`h-11 ${form.formState.errors.password ? "border-error" : ""}`}
                {...form.register("password")}
              />
              {form.formState.errors.password && (
                <p className="text-sm text-error" role="alert">
                  {form.formState.errors.password.message}
                </p>
              )}
            </div>
          </fieldset>

          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? (
              <span className="flex items-center gap-2">
                <svg
                  className="h-4 w-4 animate-spin"
                  viewBox="0 0 24 24"
                  fill="none"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                Signing in...
              </span>
            ) : (
              "Sign in"
            )}
          </Button>
        </form>
      </CardContent>

      <CardFooter className="justify-center">
        <p className="text-sm text-muted-foreground">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="font-medium text-primary hover:underline">
            Sign up
          </Link>
        </p>
      </CardFooter>

      {devCreds && devCreds.accounts.length > 0 && (
        <div
          className="mx-6 mb-6 rounded-md border border-dashed border-warning/40 bg-warning/5 p-4"
          aria-label="Development credentials"
        >
          <div className="mb-3 flex items-center gap-2">
            <span className="rounded-full bg-warning/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-warning">
              {devCreds.environment}
            </span>
            <p className="text-xs font-medium text-foreground">
              Seeded role-based accounts (dev only)
            </p>
          </div>
          <p className="mb-3 text-xs text-muted-foreground">
            Course Designer and Platform Admin accounts cannot self-register —
            they are seeded into the database on backend startup. Click a row to
            pre-fill the form, or &quot;Sign in&quot; to log in directly.
          </p>
          <ul className="space-y-2">
            {devCreds.accounts.map((acct) => (
              <li
                key={acct.email_address}
                className="rounded-md border border-border bg-background p-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary">
                        {ROLE_LABELS[acct.role] ?? acct.role}
                      </span>
                      <span className="truncate text-xs font-mono text-foreground">
                        {acct.email_address}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      <span className="font-mono">{acct.password}</span>
                      <span className="mx-1.5">·</span>
                      <span>{ROLE_ROUTES[acct.role] ?? "/"}</span>
                    </p>
                  </div>
                  <div className="flex gap-1.5">
                    <button
                      type="button"
                      onClick={() => useAccount(acct)}
                      className="rounded-md border border-border px-2 py-1 text-[11px] font-medium text-foreground hover:bg-accent"
                    >
                      Fill
                    </button>
                    <button
                      type="button"
                      onClick={() => fillAndSubmit(acct)}
                      disabled={isSubmitting}
                      className="rounded-md bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                    >
                      Sign in
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
