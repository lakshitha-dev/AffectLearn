"use client";

import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";

const step1Schema = z.object({
  emailAddress: z.string().email("Please enter a valid email address"),
  password: z
    .string()
    .min(8, "Password must be at least 8 characters")
    .regex(/[a-z]/, "Must contain a lowercase letter")
    .regex(/[A-Z]/, "Must contain an uppercase letter")
    .regex(/\d/, "Must contain a digit")
    .regex(/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/, "Must contain a special character"),
});

const step2Schema = z.object({
  firstName: z.string().min(1, "First name is required").max(100),
  lastName: z.string().min(1, "Last name is required").max(100),
  ageRange: z.string().optional(),
  degreeProgram: z.string().optional(),
});

type Step1Data = z.infer<typeof step1Schema>;
type Step2Data = z.infer<typeof step2Schema>;

export default function RegisterPage() {
  const [step, setStep] = useState(1);
  const [step1Data, setStep1Data] = useState<Step1Data | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [isDuplicateEmail, setIsDuplicateEmail] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { register: registerUser } = useAuth();
  const router = useRouter();

  const step1Form = useForm<Step1Data>({
    resolver: zodResolver(step1Schema),
    mode: "onBlur",
  });

  const step2Form = useForm<Step2Data>({
    resolver: zodResolver(step2Schema),
    mode: "onBlur",
  });

  const onStep1ValidationError = (errors: Record<string, unknown>) => {
    const firstKey = Object.keys(errors)[0] as keyof Step1Data;
    if (firstKey) step1Form.setFocus(firstKey);
  };

  const onStep2ValidationError = (errors: Record<string, unknown>) => {
    const firstKey = Object.keys(errors)[0] as keyof Step2Data;
    if (firstKey) step2Form.setFocus(firstKey);
  };

  const onStep1Submit = (data: Step1Data) => {
    setStep1Data(data);
    setServerError(null);
    setIsDuplicateEmail(false);
    setStep(2);
  };

  const onStep2Submit = async (data: Step2Data) => {
    if (!step1Data) return;
    setIsSubmitting(true);
    setServerError(null);

    try {
      await registerUser({
        ...step1Data,
        ...data,
      });
      router.push("/courses");
    } catch (err) {
      if (err instanceof ApiRequestError && err.errorCode === "DUPLICATE_EMAIL") {
        setIsDuplicateEmail(true);
        setStep(1);
      } else if (err instanceof ApiRequestError) {
        setServerError(err.message);
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
        <CardTitle className="text-xl">Create your account</CardTitle>
        <div className="flex justify-center gap-2 pt-2">
          <span
            className={`h-2 w-2 rounded-full ${step === 1 ? "bg-primary" : "bg-border"}`}
          />
          <span
            className={`h-2 w-2 rounded-full ${step === 2 ? "bg-primary" : "bg-border"}`}
          />
        </div>
      </CardHeader>

      <CardContent>
        {step === 1 && (
          <form
            onSubmit={step1Form.handleSubmit(onStep1Submit, onStep1ValidationError)}
            noValidate
            className="space-y-4"
          >
            {isDuplicateEmail && (
              <div
                className="rounded-md border border-error/30 bg-error/5 p-3 text-sm text-error"
                role="alert"
                aria-live="polite"
              >
                Already have an account?{" "}
                <Link href="/login" className="font-medium underline">
                  Sign in
                </Link>
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
                  className={`h-11 ${step1Form.formState.errors.emailAddress ? "border-error" : ""}`}
                  {...step1Form.register("emailAddress")}
                />
                {step1Form.formState.errors.emailAddress && (
                  <p className="text-sm text-error" role="alert">
                    {step1Form.formState.errors.emailAddress.message}
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
                  autoComplete="new-password"
                  className={`h-11 ${step1Form.formState.errors.password ? "border-error" : ""}`}
                  {...step1Form.register("password")}
                />
                {step1Form.formState.errors.password && (
                  <p className="text-sm text-error" role="alert">
                    {step1Form.formState.errors.password.message}
                  </p>
                )}
              </div>
            </fieldset>

            <Button type="submit" className="w-full">
              Continue
            </Button>
          </form>
        )}

        {step === 2 && (
          <form
            onSubmit={step2Form.handleSubmit(onStep2Submit, onStep2ValidationError)}
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
                <Label htmlFor="firstName">
                  First name <span className="text-muted-foreground">*</span>
                </Label>
                <Input
                  id="firstName"
                  autoComplete="given-name"
                  className={`h-11 ${step2Form.formState.errors.firstName ? "border-error" : ""}`}
                  {...step2Form.register("firstName")}
                />
                {step2Form.formState.errors.firstName && (
                  <p className="text-sm text-error" role="alert">
                    {step2Form.formState.errors.firstName.message}
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="lastName">
                  Last name <span className="text-muted-foreground">*</span>
                </Label>
                <Input
                  id="lastName"
                  autoComplete="family-name"
                  className={`h-11 ${step2Form.formState.errors.lastName ? "border-error" : ""}`}
                  {...step2Form.register("lastName")}
                />
                {step2Form.formState.errors.lastName && (
                  <p className="text-sm text-error" role="alert">
                    {step2Form.formState.errors.lastName.message}
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="ageRange">Age range</Label>
                <Controller
                  control={step2Form.control}
                  name="ageRange"
                  render={({ field }) => (
                    <Select
                      onValueChange={field.onChange}
                      value={field.value ?? ""}
                    >
                      <SelectTrigger id="ageRange" className="h-11">
                        <SelectValue placeholder="Select age range" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="18-24">18-24</SelectItem>
                        <SelectItem value="25-34">25-34</SelectItem>
                        <SelectItem value="35-44">35-44</SelectItem>
                        <SelectItem value="45-54">45-54</SelectItem>
                        <SelectItem value="55+">55+</SelectItem>
                      </SelectContent>
                    </Select>
                  )}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="degreeProgram">Degree program</Label>
                <Input
                  id="degreeProgram"
                  className="h-11"
                  {...step2Form.register("degreeProgram")}
                />
              </div>
            </fieldset>

            <div className="flex flex-col gap-2">
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
                    Creating account...
                  </span>
                ) : (
                  "Create account"
                )}
              </Button>
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={() => setStep(1)}
              >
                Back
              </Button>
            </div>
          </form>
        )}
      </CardContent>

      <CardFooter className="justify-center">
        <p className="text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </CardFooter>
    </Card>
  );
}
