"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AuthGuard } from "@/components/shared/auth-guard";
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
  const [collapsed, setCollapsed] = useState(false);

  return (
    <AuthGuard allowedRoles={["learner"]}>
      <div className="flex min-h-screen">
        <aside
          className={cn(
            "shrink-0 border-r border-border bg-surface transition-all",
            collapsed ? "w-12" : "w-60"
          )}
        >
          <div className="flex items-center justify-between p-4">
            {!collapsed && (
              <span className="text-sm font-semibold text-foreground">
                AffectLearn
              </span>
            )}
            <button
              onClick={() => setCollapsed(!collapsed)}
              className="rounded p-1 text-muted-foreground hover:bg-border"
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {collapsed ? ">" : "<"}
            </button>
          </div>
          <nav className="mt-2">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center px-4 py-2.5 text-sm text-foreground transition-colors hover:bg-border/50",
                  pathname === item.href && "bg-primary-soft font-medium text-primary"
                )}
                title={collapsed ? item.label : undefined}
              >
                {collapsed ? (
                  <span className="mx-auto text-xs font-medium">{item.label[0]}</span>
                ) : (
                  item.label
                )}
              </Link>
            ))}
          </nav>
        </aside>
        <main className="flex-1 bg-background">
          <div className="mx-auto max-w-3xl p-8">{children}</div>
        </main>
      </div>
    </AuthGuard>
  );
}
