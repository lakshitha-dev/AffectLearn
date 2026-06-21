"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AuthGuard } from "@/components/shared/auth-guard";
import { TopBar } from "@/components/shared/TopBar";
import { cn } from "@/lib/cn";

// Dashboard is the analytics landing (Story 7.2). Order follows the UX spec:
// Dashboard / Courses / Analytics / Settings. `Content Editor` is folded under
// Courses (the courses-editor route) per the AC's four-item requirement.
const NAV_ITEMS = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Courses", href: "/courses-editor" },
  { label: "Analytics", href: "/analytics" },
  { label: "Settings", href: "/settings" },
];

export default function DesignerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <AuthGuard allowedRoles={["course_designer", "admin"]}>
      <TopBar />
      <div className="flex min-h-[calc(100vh-3.5rem)]">
        {/* Persistent dark 240px sidebar. Background uses the `--secondary` token
            (Slate 900 in light mode); `text-background` is its readable inverse in
            BOTH themes (--background is white in light / Slate 900 in dark, the
            mirror of --secondary), so the active white-on-dark / dark-on-light
            treatment reads correctly under Story 1.4 dual theming. */}
        <aside className="w-60 shrink-0 bg-secondary text-background">
          <div className="px-6 py-4">
            <p className="text-xs font-medium uppercase tracking-wider text-background/60">
              Course Designer
            </p>
          </div>
          <nav className="mt-4">
            {NAV_ITEMS.map((item) => {
              const isActive =
                pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "flex items-center px-6 py-3 text-sm text-background/70 transition-colors hover:bg-background/10 hover:text-background",
                    isActive &&
                      "border-l-[3px] border-primary bg-background/5 font-medium text-background"
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </aside>
        <main className="flex-1 bg-background p-8">{children}</main>
      </div>
    </AuthGuard>
  );
}
