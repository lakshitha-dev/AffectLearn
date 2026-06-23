"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

const schema = z.object({
  emailAddress: z.string().email("Please enter a valid email address"),
});

type FormData = z.infer<typeof schema>;

export default function ForgotPasswordPage() {
  const { forgotPassword } = useAuth();
  const [submitted, setSubmitted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const form = useForm<FormData>({
    resolver: zodResolver(schema),
    mode: "onBlur",
  });

  const onSubmit = async (data: FormData) => {
    setIsSubmitting(true);
    try {
      await forgotPassword(data.emailAddress);
    } finally {
      // Always show the same confirmation (no account enumeration).
      setSubmitted(true);
      setIsSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <Card className="rounded-none border-border shadow-sm">
        <CardHeader>
          <CardTitle className="text-2xl tracking-tight">Check your email</CardTitle>
          <CardDescription>
            If an account matches that email, we&apos;ve sent a link to reset your password.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/login" className="text-sm font-medium text-primary hover:underline">
            Back to sign in
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="rounded-none border-border shadow-sm">
      <CardHeader>
        <CardTitle className="text-2xl tracking-tight">Reset your password</CardTitle>
        <CardDescription>
          Enter your email and we&apos;ll send you a link to choose a new password.
        </CardDescription>
      </CardHeader>

      <CardContent>
        <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-4">
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

          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Sending..." : "Send reset link"}
          </Button>
        </form>
      </CardContent>

      <CardFooter className="justify-center">
        <p className="text-sm text-muted-foreground">
          Remembered it?{" "}
          <Link href="/login" className="font-medium text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </CardFooter>
    </Card>
  );
}
