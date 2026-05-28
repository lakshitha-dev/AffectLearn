"use client";

import { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { Sun, Moon, Monitor, LogOut, ChevronDown } from "lucide-react";
import { useSessionStore } from "@/stores/session-store";

const THEME_CYCLE = ["light", "dark", "system"] as const;

function ThemeIcon({ resolvedTheme, theme }: { resolvedTheme?: string; theme?: string }) {
  if (theme === "system") return <Monitor className="h-5 w-5" />;
  if (resolvedTheme === "dark") return <Moon className="h-5 w-5" />;
  return <Sun className="h-5 w-5" />;
}

function themeLabel(theme?: string, resolvedTheme?: string): string {
  if (theme === "system") return `System (${resolvedTheme})`;
  return theme === "dark" ? "Dark" : "Light";
}

function UserMenu() {
  const { user, clearSession } = useSessionStore();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  if (!user) return null;

  const initials = `${user.firstName[0] ?? ""}${user.lastName[0] ?? ""}`.toUpperCase();

  function handleLogout() {
    clearSession();
    router.replace("/login");
  }

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-haspopup="true"
        aria-expanded={open}
        aria-label="User menu"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
          {initials}
        </span>
        <span className="hidden font-medium sm:inline">
          {user.firstName}
        </span>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-50 mt-1 w-52 overflow-hidden rounded-md border border-border bg-background shadow-lg"
        >
          <div className="border-b border-border px-4 py-3">
            <p className="text-sm font-medium text-foreground">
              {user.firstName} {user.lastName}
            </p>
            <p className="mt-0.5 truncate text-xs text-muted-foreground">{user.emailAddress}</p>
          </div>
          <button
            role="menuitem"
            onClick={handleLogout}
            className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-foreground transition-colors hover:bg-accent"
          >
            <LogOut className="h-4 w-4 text-muted-foreground" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export function TopBar() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  function cycleTheme() {
    const currentIndex = THEME_CYCLE.indexOf(theme as (typeof THEME_CYCLE)[number]);
    const nextIndex = (currentIndex + 1) % THEME_CYCLE.length;
    setTheme(THEME_CYCLE[nextIndex]);
  }

  return (
    <header className="flex h-14 shrink-0 items-center border-b border-border bg-background px-4">
      <div className="flex items-center gap-2">
        <span className="text-base font-semibold text-foreground">AffectLearn</span>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <button
          onClick={cycleTheme}
          className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          aria-label={mounted ? `Theme: ${themeLabel(theme, resolvedTheme)}. Click to change.` : "Toggle theme"}
        >
          {mounted ? (
            <ThemeIcon resolvedTheme={resolvedTheme} theme={theme} />
          ) : (
            <Sun className="h-5 w-5" />
          )}
        </button>
        <UserMenu />
      </div>
    </header>
  );
}
