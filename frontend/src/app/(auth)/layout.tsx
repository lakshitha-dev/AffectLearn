"use client";

import { GuestGuard } from "@/components/shared/guest-guard";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <GuestGuard>
      <div className="flex min-h-screen items-center justify-center bg-background px-4 py-12">
        <div className="w-full max-w-md">
          <div className="mb-8 text-center">
            <h1 className="text-2xl font-bold text-foreground">AffectLearn</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Adaptive e-learning platform
            </p>
          </div>
          {children}
        </div>
      </div>
    </GuestGuard>
  );
}
