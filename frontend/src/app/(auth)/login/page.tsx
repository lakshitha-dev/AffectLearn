"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
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
  learner: "/(learner)/courses",
  designer: "/(designer)/analytics",
  admin: "/(admin)/users",
};

export default function LoginPage() {
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { login } = useAuth();
  const router = useRouter();

  const form = useForm<LoginData>({
    resolver: zodResolver(loginSchema),
    mode: "onBlur",
  });

  const onSubmit = async (data: LoginData) => {
    setIsSubmitting(true);
    setServerError(null);

    try {
      const user = await login(data);
      const redirect = ROLE_REDIRECTS[user.role] ?? "/(learner)/courses";
      router.push(redirect);
    } catch (err) {
      if (err instanceof ApiRequestError && err.errorCode === "INVALID_CREDENTIALS") {
        setServerError("Invalid email or password. Please try again.");
      } else {
        setServerError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">Sign in to your account</CardTitle>
      </CardHeader>

      <CardContent>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
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
              <Label htmlFor="password">
                Password <span className="text-muted-foreground">*</span>
              </Label>
              <Input
                id="password"
                type="password"
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
    </Card>
  );
}
