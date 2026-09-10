"use client";

import { useCallback, useEffect, useRef } from "react";

import { apiFetch } from "@/lib/api-client";

/**
 * Records every VISIT to a section, not only its completion.
 *
 * `section_progress` holds one row per (learner, section) with a single `completed_at`. A
 * learner who reads a section, moves on, comes back confused and re-reads it leaves exactly the
 * same row as one who read it once and understood it — and a section revisited but never
 * completed, which is the case most worth seeing, leaves no trace at all.
 *
 * Returning to material is one of the few struggle signals a paginated one-section-per-page
 * reader produces reliably, so it is worth its own record.
 *
 * BEST-EFFORT BY DESIGN. Every call is fire-and-forget and every failure is swallowed:
 * instrumentation must never interrupt, block or error a learner who is trying to read. A lost
 * visit is a lost row, not a lost lesson.
 *
 * OPEN VISITS ARE AMBIGUOUS. A visit with no `leftAt` means either "still here" or "the browser
 * was closed and the closing call never arrived". The two are indistinguishable from the server,
 * which is why the model documents that readers must treat an open visit as unknown-duration
 * rather than assuming it ran until the next one began.
 */

// `skip` is the system advancing the learner after they accepted a `skip_ahead`
// adaptation, as distinct from `next`, which is the learner choosing to move on. The two
// mean different things when reading the visit log — one is a decision the learner made
// and the other is one made for them — and they cannot be told apart after the fact.
export type SectionEntrySource = "next" | "back" | "resume" | "direct" | "skip";

interface OpenVisit {
  id: string;
  sectionId: string;
  enteredAt: number;
}

async function openVisit(
  sectionId: string,
  entrySource: SectionEntrySource,
): Promise<OpenVisit | null> {
  try {
    const res = await apiFetch<{ id: string; sectionId: string }>("/section-visits", {
      method: "POST",
      body: JSON.stringify({ sectionId, entrySource }),
    });
    return { id: res.id, sectionId, enteredAt: Date.now() };
  } catch {
    return null;
  }
}

async function closeVisit(visit: OpenVisit): Promise<void> {
  try {
    await apiFetch(`/section-visits/${visit.id}/close`, {
      method: "POST",
      body: JSON.stringify({
        durationSeconds: Math.max(0, Math.round((Date.now() - visit.enteredAt) / 1000)),
      }),
    });
  } catch {
    /* best-effort */
  }
}

export function useSectionVisits(sectionId: string | undefined) {
  const openRef = useRef<OpenVisit | null>(null);
  // How the learner arrived at the NEXT section. Set by the navigation handlers before they
  // change the section; defaults to "direct" for the first section of a page load, which is
  // either a fresh start or a resume and cannot be told apart from here.
  const sourceRef = useRef<SectionEntrySource>("direct");
  // Guards React's development double-effect, which would otherwise open two visits for every
  // section and double every revisit count in local testing.
  const inFlightRef = useRef<string | null>(null);

  const setEntrySource = useCallback((source: SectionEntrySource) => {
    sourceRef.current = source;
  }, []);

  useEffect(() => {
    if (!sectionId || inFlightRef.current === sectionId) return;
    inFlightRef.current = sectionId;

    const previous = openRef.current;
    openRef.current = null;
    if (previous) void closeVisit(previous);

    const source = sourceRef.current;
    // Subsequent moves are forward unless a handler says otherwise, so the default resets here
    // rather than leaving "direct" to be attributed to every later section.
    sourceRef.current = "next";

    let cancelled = false;
    void openVisit(sectionId, source).then((visit) => {
      if (cancelled) {
        // The learner navigated away before the round trip finished. Close it immediately so it
        // does not linger as a permanently open visit.
        if (visit) void closeVisit(visit);
        return;
      }
      openRef.current = visit;
    });

    return () => {
      cancelled = true;
    };
  }, [sectionId]);

  // Closing on unload is a best-effort courtesy, not a guarantee: browsers curtail work during
  // `pagehide`, so this will sometimes not complete. That is exactly the case the model's
  // "open means unknown, not infinite" note exists for.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onHide = () => {
      const visit = openRef.current;
      openRef.current = null;
      if (visit) void closeVisit(visit);
    };
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      onHide();
    };
  }, []);

  return { setEntrySource };
}
