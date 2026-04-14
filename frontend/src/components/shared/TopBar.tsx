"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { Sun, Moon, Monitor } from "lucide-react";

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
          className="inline-flex h-11 w-11 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          aria-label={mounted ? `Theme: ${themeLabel(theme, resolvedTheme)}. Click to change.` : "Toggle theme"}
        >
          {mounted ? (
            <ThemeIcon resolvedTheme={resolvedTheme} theme={theme} />
          ) : (
            <Sun className="h-5 w-5" />
          )}
        </button>
      </div>
    </header>
  );
}
