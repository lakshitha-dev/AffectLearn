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

  if (!hasHydrated) return null;
  if (!isAuthenticated) return null;
  if (!hasAccess) return null;

  return <>{children}</>;
}
