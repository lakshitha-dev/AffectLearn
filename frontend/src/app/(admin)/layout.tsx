"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AuthGuard } from "@/components/shared/auth-guard";
import { TopBar } from "@/components/shared/TopBar";
import { cn } from "@/lib/cn";

const NAV_ITEMS = [
  { label: "Users", href: "/users" },
  { label: "A/B Groups", href: "/ab-groups" },
  { label: "Pipeline Monitor", href: "/monitor" },
  { label: "System Health", href: "/system-health" },
  { label: "Data Export", href: "/data-export" },
  { label: "Settings", href: "/admin-settings" },
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
      <div className="flex min-h-[calc(100vh-3.5rem)]">
        <aside className="w-60 shrink-0 bg-slate-900 text-white">
          <div className="px-6 py-4">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Administration</p>
          </div>
          <nav className="mt-4">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center px-6 py-3 text-sm text-slate-300 transition-colors hover:bg-white/10 hover:text-white",
                  pathname === item.href &&
                    "border-l-[3px] border-primary bg-white/5 font-medium text-white"
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </aside>
        <main className="flex-1 bg-background p-8">{children}</main>
      </div>
    </AuthGuard>
  );
}
