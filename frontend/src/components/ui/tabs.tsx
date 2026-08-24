"use client";

/**
 * Minimal accessible tabs.
 *
 * `@radix-ui/react-tabs` is not a dependency and this needs two tabs, so it is hand-rolled
 * rather than adding a package — same call the admin users page made for its modal.
 *
 * Keyboard behaviour follows the ARIA tabs pattern: Left/Right move between tabs, Home/End
 * jump to the ends. Panels are always mounted so a tab switch does not tear down the SSE
 * stream in the Live tab and lose its event backlog.
 */

import { useId, useRef, useState } from "react";
import { cn } from "@/lib/cn";

export interface TabSpec {
  value: string;
  label: string;
}

interface TabsProps {
  tabs: TabSpec[];
  defaultValue?: string;
  children: (active: string) => React.ReactNode;
  className?: string;
}

export function Tabs({ tabs, defaultValue, children, className }: TabsProps) {
  const [active, setActive] = useState(defaultValue ?? tabs[0]?.value ?? "");
  const baseId = useId();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(e: React.KeyboardEvent) {
    const i = tabs.findIndex((t) => t.value === active);
    if (i < 0) return;
    let next = i;
    if (e.key === "ArrowRight") next = (i + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    else return;
    e.preventDefault();
    const value = tabs[next].value;
    setActive(value);
    refs.current[value]?.focus();
  }

  return (
    <div className={className}>
      <div
        role="tablist"
        aria-label="Monitor views"
        onKeyDown={onKeyDown}
        className="mb-6 flex gap-1 border-b border-border"
      >
        {tabs.map((t) => {
          const selected = t.value === active;
          return (
            <button
              key={t.value}
              ref={(el) => {
                refs.current[t.value] = el;
              }}
              role="tab"
              id={`${baseId}-tab-${t.value}`}
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${t.value}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(t.value)}
              className={cn(
                "-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors",
                selected
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {tabs.map((t) => (
        <div
          key={t.value}
          role="tabpanel"
          id={`${baseId}-panel-${t.value}`}
          aria-labelledby={`${baseId}-tab-${t.value}`}
          hidden={t.value !== active}
        >
          {/* Always mounted: hiding rather than unmounting keeps the SSE stream alive. */}
          {children(t.value)}
        </div>
      ))}
    </div>
  );
}
