"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { cn } from "@/lib/cn";
import { useWebcamStore } from "@/stores/webcam-store";
import type { WebcamMode } from "@/stores/webcam-store";

const MODE_CONFIG: Record<WebcamMode, { dot: string; label: string; dotClass: string }> = {
  adaptive: { dot: "bg-success", label: "Adaptive mode active", dotClass: "bg-success" },
  behavioral: { dot: "bg-primary", label: "Behavioral mode", dotClass: "bg-primary" },
  error: { dot: "bg-warning", label: "Switched to behavioral mode", dotClass: "bg-warning" },
};

export function WebcamIndicator() {
  const { mode, setMode } = useWebcamStore();
  const [expanded, setExpanded] = useState(false);
  const [visible, setVisible] = useState(true);
  const dismissTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-dismiss error state after 5s
  useEffect(() => {
    if (mode === "error") {
      if (dismissTimeout.current) clearTimeout(dismissTimeout.current);
      dismissTimeout.current = setTimeout(() => {
        setMode("behavioral");
        setVisible(true);
      }, 5000);
    }
    return () => {
      if (dismissTimeout.current) clearTimeout(dismissTimeout.current);
    };
  }, [mode, setMode]);

  if (!visible) return null;

  const config = MODE_CONFIG[mode];

  return (
    <div
      className="fixed bottom-4 right-4 z-30"
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => setExpanded(false)}
    >
      <div
        className={cn(
          "flex items-center gap-2 rounded-full border border-border bg-background shadow-md px-3 py-1.5 text-xs font-medium",
          "transition-all duration-200 cursor-default"
        )}
      >
        <span className={cn("h-2 w-2 rounded-full shrink-0 animate-pulse", config.dotClass)} />
        <span className="text-foreground">{config.label}</span>

        {expanded && (
          <div className="ml-1 flex items-center gap-2 border-l border-border pl-2 text-muted-foreground">
            <span className="hidden sm:inline">No video is stored.</span>
            {/*
              Was `/onboarding?step=webcam`. The wizard ignores `step` entirely and always starts
              at "welcome", and it redirects anyone who has already consented straight to
              `/courses` — so this link silently dumped the learner on the course list instead of
              anywhere they could change the setting. `/profile` is where the webcam toggle
              actually lives.
            */}
            <Link href="/profile" className="text-primary hover:underline text-xs">
              Settings
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}