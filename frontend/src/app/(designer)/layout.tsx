"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AuthGuard } from "@/components/shared/auth-guard";
import { cn } from "@/lib/cn";

const NAV_ITEMS = [
  { label: "Courses", href: "/courses-editor" },
  { label: "Analytics", href: "/analytics" },
  { label: "Content Editor", href: "/content-editor" },
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
      <div className="flex min-h-screen">
        <aside className="w-60 shrink-0 bg-secondary text-white">
          <div className="p-6">
            <h2 className="text-lg font-bold">AffectLearn</h2>
            <p className="mt-1 text-xs text-muted-foreground">Course Designer</p>
          </div>
          <nav className="mt-4">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center px-6 py-3 text-sm transition-colors hover:bg-white/10",
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
