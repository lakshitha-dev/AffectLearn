"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { Sun, Moon } from "lucide-react";

interface ThemeToggleProps {
  /** Extra classes merged onto the button (lets the landing nav restyle it). */
  className?: string;
}

/**
 * Compact light/dark theme toggle reusing the next-themes pattern from TopBar.
 * Guards against SSR/hydration mismatch with a `mounted` check — until the
 * client has hydrated we render a stable placeholder icon.
 */
export function ThemeToggle({ className }: ThemeToggleProps = {}) {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const isDark = mounted && resolvedTheme === "dark";

  function toggleTheme() {
    setTheme(isDark ? "light" : "dark");
  }

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={
        className ??
        "inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      }
      aria-label={
        mounted
          ? `Switch to ${isDark ? "light" : "dark"} theme`
          : "Toggle theme"
      }
    >
      {isDark ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
    </button>
  );
}
