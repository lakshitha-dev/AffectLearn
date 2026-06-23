"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/session-store";

const ROLE_DASHBOARDS: Record<string, string> = {
  learner: "/courses",
  course_designer: "/analytics",
  admin: "/users",
};

export function GuestGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { accessToken, expiresAt, user, hasHydrated } = useSessionStore();
  const isAuthenticated =
    accessToken !== null && expiresAt !== null && Date.now() < expiresAt;

  useEffect(() => {
    // Wait for rehydration before redirecting authenticated users away (mirrors AuthGuard).
    if (!hasHydrated) return;
    if (isAuthenticated && user) {
      const redirect = ROLE_DASHBOARDS[user.role] ?? "/courses";
      router.replace(redirect);
    }
  }, [hasHydrated, isAuthenticated, user, router]);

  if (hasHydrated && isAuthenticated && user) return null;

  return <>{children}</>;
}
