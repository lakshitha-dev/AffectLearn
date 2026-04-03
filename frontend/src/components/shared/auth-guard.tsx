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
  const { accessToken, expiresAt, user } = useSessionStore();
  const isAuthenticated =
    accessToken !== null && expiresAt !== null && Date.now() < expiresAt;

  const hasAccess =
    !allowedRoles || (user && allowedRoles.includes(user.role));

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }

    if (allowedRoles && user && !allowedRoles.includes(user.role)) {
      const redirect = ROLE_DASHBOARDS[user.role] ?? "/courses";
      router.replace(redirect);
    }
  }, [isAuthenticated, user, allowedRoles, router]);

  if (!isAuthenticated) return null;
  if (!hasAccess) return null;

  return <>{children}</>;
}
