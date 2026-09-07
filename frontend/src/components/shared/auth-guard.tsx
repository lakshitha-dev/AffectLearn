"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/session-store";

const ROLE_DASHBOARDS: Record<string, string> = {
  learner: "/courses",
  course_designer: "/analytics",
  admin: "/users",
};

interface AuthGuardProps {
  children: React.ReactNode;
  allowedRoles?: string[];
}

export function AuthGuard({ children, allowedRoles }: AuthGuardProps) {
  const router = useRouter();
  const { accessToken, expiresAt, user, hasHydrated } = useSessionStore();
  const isAuthenticated =
    accessToken !== null && expiresAt !== null && Date.now() < expiresAt;

  const hasAccess =
    !allowedRoles || (user && allowedRoles.includes(user.role));

  useEffect(() => {
    // Wait until the persisted session is rehydrated before deciding — otherwise we
    // redirect on the initial null state and bounce with the guest guard.
    if (!hasHydrated) return;

    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }

    if (allowedRoles && user && !allowedRoles.includes(user.role)) {
      const redirect = ROLE_DASHBOARDS[user.role] ?? "/courses";
      router.replace(redirect);
    }
  }, [hasHydrated, isAuthenticated, user, allowedRoles, router]);

  // WHY THERE IS NO SERVER-SIDE MIDDLEWARE DOING THIS
  //
  // The session lives in `localStorage`, which Next.js middleware cannot read — it runs on the
  // server and sees only cookies. Guarding these routes server-side would mean moving the access
  // token into a cookie, which changes the CSRF posture of every mutating request in the app and
  // is an auth redesign rather than a rendering fix. The real boundary is the API: every guarded
  // endpoint independently rejects an unauthenticated or wrong-role caller, and `e2e/rbac.spec.ts`
  // tests that directly. This guard decides what to DRAW, not what may be read.
  //
  // What it should not draw is nothing. Returning `null` while the decision is pending rendered a
  // blank page on every load of every guarded route — indistinguishable from a broken app for the
  // moment it lasts, and longer on a slow device.
  if (!hasHydrated) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex min-h-screen items-center justify-center"
      >
        <span className="sr-only">Loading</span>
        <span className="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-primary" />
      </div>
    );
  }

  // Past this point a redirect is already queued by the effect above, so this is the frame or two
  // before the router moves — a spinner reads as "going somewhere", a blank page reads as broken.
  if (!isAuthenticated || !hasAccess) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex min-h-screen items-center justify-center"
      >
        <span className="sr-only">Redirecting</span>
        <span className="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-primary" />
      </div>
    );
  }

  return <>{children}</>;
}
