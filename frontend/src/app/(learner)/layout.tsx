"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BookOpen, ChevronLeft, ChevronRight, TrendingUp, User, X } from "lucide-react";
import { AuthGuard } from "@/components/shared/auth-guard";
import { TopBar } from "@/components/shared/TopBar";
import { useSessionStore } from "@/stores/session-store";
import { useUiStore } from "@/stores/ui-store";
import { useWebcamStore } from "@/stores/webcam-store";
import { cn } from "@/lib/cn";

const NAV_ITEMS = [
  { label: "Courses", href: "/courses", icon: BookOpen },
  { label: "My Progress", href: "/progress", icon: TrendingUp },
  { label: "Profile", href: "/profile", icon: User },
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
  const initWebcamMode = useWebcamStore((s) => s.initFromUser);
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

  // Restore the webcam capture mode from the learner's saved preference. The
  // webcam store is in-memory and defaults to "behavioral"; without this, the
  // "adaptive" mode set during onboarding is lost on navigation/reload and the
  // facial-capture hook (useMediaPipe) never opens the camera on the lesson page.
  useEffect(() => {
    if (user && user.role === "learner") {
      initWebcamMode(user.webcamEnabled ?? false);
    }
  }, [user, initWebcamMode]);

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
            // Off-canvas drawer below lg; in-flow sidebar at lg+ (relative so the
            // floating edge toggle can anchor to the sidebar's right edge).
            "fixed inset-y-0 left-0 top-14 z-50 w-64 border-r border-border bg-surface",
            "lg:relative lg:top-0 lg:z-auto lg:translate-x-0",
            hydrated && "transition-all duration-200",
            mobileNavOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
            collapsed ? "lg:w-16" : "lg:w-60"
          )}
        >
          {/* Close drawer — mobile only. On desktop the sidebar has no header row;
              collapsing is handled by the floating edge toggle below. */}
          <div className="flex items-center justify-end p-4 lg:hidden">
            <button
              onClick={() => setMobileNavOpen(false)}
              className="rounded p-1 text-muted-foreground hover:bg-border"
              aria-label="Close navigation menu"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Collapse toggle — floating tab straddling the sidebar's right edge (desktop only) */}
          <button
            onClick={toggleSidebar}
            className="absolute -right-3 top-6 z-10 hidden h-6 w-6 items-center justify-center rounded-full border border-border bg-background text-muted-foreground shadow-sm transition-colors hover:border-primary hover:text-foreground lg:flex"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? (
              <ChevronRight className="h-3.5 w-3.5" />
            ) : (
              <ChevronLeft className="h-3.5 w-3.5" />
            )}
          </button>

          <nav className="flex flex-col gap-1 px-2 pt-2 lg:pt-4">
            {NAV_ITEMS.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileNavOpen(false)}
                  title={collapsed ? item.label : undefined}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-foreground transition-colors hover:bg-border/50",
                    collapsed && "lg:justify-center lg:gap-0 lg:px-0",
                    isActive && "bg-primary-soft font-medium text-primary"
                  )}
                >
                  {isActive && (
                    <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r bg-primary" aria-hidden />
                  )}
                  <item.icon className="h-5 w-5 shrink-0" />
                  <span className={cn(collapsed && "lg:hidden")}>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </aside>
        <main className="flex-1 bg-background">
          <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8">{children}</div>
        </main>
      </div>
    </AuthGuard>
  );
}
