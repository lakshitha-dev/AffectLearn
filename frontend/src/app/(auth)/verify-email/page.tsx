"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";

const ROLE_REDIRECTS: Record<string, string> = {
  learner: "/courses",
  course_designer: "/analytics",
  admin: "/users",
};

type Status = "verifying" | "success" | "error";

function VerifyEmailInner() {
  const params = useSearchParams();
  const router = useRouter();
  const { verifyEmail } = useAuth();
  const [status, setStatus] = useState<Status>("verifying");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return; // guard React 18 StrictMode double-invoke
    ran.current = true;

    const token = params.get("token");
    if (!token) {
      setStatus("error");
      setErrorMessage("This verification link is missing its token.");
      return;
    }

    verifyEmail(token)
      .then((user) => {
        setStatus("success");
        const needsOnboarding = user.role === "learner" && !user.consentGivenAt;
        const redirect = needsOnboarding
          ? "/onboarding"
          : (ROLE_REDIRECTS[user.role] ?? "/courses");
        router.push(redirect);
      })
      .catch((err) => {
        setStatus("error");
        if (err instanceof ApiRequestError && err.errorCode === "TOKEN_EXPIRED") {
          setErrorMessage("This verification link has expired. Request a new one from the sign in page.");
        } else if (err instanceof ApiRequestError && err.errorCode === "TOKEN_USED") {
          setErrorMessage("This link has already been used. Try signing in.");
        } else {
          setErrorMessage("This verification link is invalid. Request a new one from the sign in page.");
        }
      });
  }, [params, router, verifyEmail]);

  return (
    <Card className="rounded-none border-border shadow-sm">
      <CardHeader>
        <CardTitle className="text-2xl tracking-tight">
          {status === "error" ? "Verification failed" : "Verifying your email"}
        </CardTitle>
        <CardDescription>
          {status === "verifying" && "Just a moment while we confirm your email address."}
          {status === "success" && "Your email is verified — taking you in."}
          {status === "error" && errorMessage}
        </CardDescription>
      </CardHeader>
      {status === "error" && (
        <CardContent>
          <Link href="/login" className="text-sm font-medium text-primary hover:underline">
            Go to sign in
          </Link>
        </CardContent>
      )}
    </Card>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailInner />
    </Suspense>
  );
}
