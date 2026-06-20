"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { X } from "lucide-react";
import { AuthGuard } from "@/components/shared/auth-guard";
import { TopBar } from "@/components/shared/TopBar";
import { useSessionStore } from "@/stores/session-store";
import { useUiStore } from "@/stores/ui-store";
import { cn } from "@/lib/cn";

const NAV_ITEMS = [
  { label: "Courses", href: "/courses" },
  { label: "My Progress", href: "/progress" },
  { label: "Profile", href: "/profile" },
];

export default function LearnerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { sidebarCollapsed: collapsed, toggleSidebar } = useUiStore();
  const user = useSessionStore((s) => s.user);
  const [hydrated, setHydrated] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => setHydrated(true), []);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => setMobileNavOpen(false), [pathname]);

  // Close the mobile drawer on Escape.
  useEffect(() => {
    if (!mobileNavOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMobileNavOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileNavOpen]);

  // Force any learner without recorded consent through the onboarding wizard
  // before they can access learner-area pages.
  useEffect(() => {
    if (user && user.role === "learner" && !user.consentGivenAt) {
      router.replace("/onboarding");
    }
  }, [user, router]);

  // The immersive lesson route supplies its own full shell (top bar, course-outline
  // sidebar, webcam indicator, focus mode) via its nested layout. Wrapping it in the
  // standard learner chrome too would render a page-within-a-page — two top bars and
  // two sidebars — so step aside and let that layout own the screen.
  const isLessonView = pathname.includes("/lessons/");
  if (isLessonView) {
    return <>{children}</>;
  }

  return (
    <AuthGuard allowedRoles={["learner"]}>
      <TopBar onMenuClick={() => setMobileNavOpen(true)} />
      <div className="flex min-h-[calc(100vh-3.5rem)]">
        {/* Backdrop — mobile only, shown when the drawer is open */}
        {mobileNavOpen && (
          <div
            className="fixed inset-0 top-14 z-40 bg-black/40 lg:hidden"
            onClick={() => setMobileNavOpen(false)}
            aria-hidden
          />
        )}

        <aside
          className={cn(
            // Off-canvas drawer below lg; static in-flow sidebar at lg+
            "fixed inset-y-0 left-0 top-14 z-50 w-64 border-r border-border bg-surface",
            "lg:static lg:top-0 lg:z-auto lg:translate-x-0",
            hydrated && "transition-all duration-200",
            mobileNavOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
            collapsed ? "lg:w-12" : "lg:w-60"
          )}
        >
          <div className="flex items-center justify-between p-4">
            <span
              className={cn(
                "text-sm font-semibold text-foreground",
                collapsed && "lg:hidden"
              )}
            >
              AffectLearn
            </span>
            {/* Collapse toggle — desktop only */}
            <button
              onClick={toggleSidebar}
              className="hidden rounded p-1 text-muted-foreground hover:bg-border lg:block"
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {collapsed ? ">" : "<"}
            </button>
            {/* Close drawer — mobile only */}
            <button
              onClick={() => setMobileNavOpen(false)}
              className="rounded p-1 text-muted-foreground hover:bg-border lg:hidden"
              aria-label="Close navigation menu"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <nav className="mt-2">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileNavOpen(false)}
                className={cn(
                  "flex items-center px-4 py-2.5 text-sm text-foreground transition-colors hover:bg-border/50",
                  pathname === item.href && "bg-primary-soft font-medium text-primary"
                )}
                title={collapsed ? item.label : undefined}
              >
                <span className={cn(collapsed && "lg:hidden")}>{item.label}</span>
                {collapsed && (
                  <span className="mx-auto hidden text-xs font-medium lg:inline">
                    {item.label[0]}
                  </span>
                )}
              </Link>
            ))}
          </nav>
        </aside>
        <main className="flex-1 bg-background">
          <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8">{children}</div>
        </main>
      </div>
    </AuthGuard>
  );
}
