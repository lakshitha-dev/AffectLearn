"use client";

import { useEffect, useState } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

/**
 * Returns `true` when the user has requested reduced motion
 * (`prefers-reduced-motion: reduce`).
 *
 * Story 5.4 (Inline Adaptive Hint Callout) uses this to skip the JS-timed
 * fade-out delay before unmount so dismiss is instant for those users. The
 * visual enter/exit transitions are CSS/Tailwind driven, so the global
 * `@media (prefers-reduced-motion: reduce)` rule in `globals.css` already
 * clamps their durations to ~0; this hook only guards the JS sequencing.
 *
 * SSR/jsdom-safe: feature-detects `window.matchMedia` and defaults to `false`
 * (no reduce) when it is unavailable, so it never throws during render or in
 * test environments that do not implement `matchMedia`.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mql = window.matchMedia(QUERY);
    setReduced(mql.matches);

    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    // Older Safari only supports addListener/removeListener.
    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    }
    mql.addListener(onChange);
    return () => mql.removeListener(onChange);
  }, []);

  return reduced;
}
