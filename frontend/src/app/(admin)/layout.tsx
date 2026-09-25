"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  FlaskConical,
  HeartPulse,
  Download,
  Settings,
  ShieldCheck,
  UserCircle,
  Users,
  type LucideIcon,
} from "lucide-react";
import { AuthGuard } from "@/components/shared/auth-guard";
import { TopBar } from "@/components/shared/TopBar";
import { cn } from "@/lib/cn";

const NAV_ITEMS: { label: string; href: string; icon: LucideIcon; live?: boolean }[] = [
  { label: "Users", href: "/users", icon: Users },
  { label: "A/B Groups", href: "/ab-groups", icon: FlaskConical },
  { label: "Pipeline Monitor", href: "/monitor", icon: Activity, live: true },
  { label: "System Health", href: "/system-health", icon: HeartPulse },
  { label: "Data Export", href: "/data-export", icon: Download },
  // Whether the ground-truth labels the study rests on are worth resting on (Story 8.6).
  { label: "Label Quality", href: "/quality", icon: ShieldCheck },
  { label: "Settings", href: "/admin-settings", icon: Settings },
  // The admin's own profile/password, distinct from the system-wide gate configuration above.
  { label: "Account", href: "/account", icon: UserCircle },
];

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <AuthGuard allowedRoles={["admin"]}>
      <TopBar />
      {/* `admin-theme` switches the whole admin area to the Daylight palette (globals.css). */}
      <div className="admin-theme flex min-h-[calc(100vh-3.5rem)] bg-background text-foreground">
        <aside className="w-60 shrink-0 border-r border-border bg-card/70 backdrop-blur">
          <div className="px-5 pb-2 pt-6">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Administration
            </p>
          </div>
          <nav className="flex flex-col gap-1 px-3 py-2">
            {NAV_ITEMS.map((item) => {
              const active = pathname === item.href;
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    active
                      ? "bg-primary-soft font-semibold text-primary"
                      : "text-muted-foreground hover:bg-surface hover:text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span className="flex-1">{item.label}</span>
                  {item.live && (
                    <span className="relative flex h-2 w-2" aria-hidden="true">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success/60" />
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>
        </aside>
        <main className="min-w-0 flex-1 bg-background p-6 lg:p-8">{children}</main>
      </div>
    </AuthGuard>
  );
}
