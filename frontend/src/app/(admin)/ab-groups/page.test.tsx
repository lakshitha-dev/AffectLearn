/**
 * Tests for the A/B Groups page.
 *
 * The version this replaced was hardcoded mock data claiming "learners are automatically assigned
 * to groups during registration based on a balanced randomization algorithm" — an algorithm that
 * does not exist. So the first regression to guard is that the page reports the REAL procedure.
 *
 * The second is subtler and had already shipped: every REST response model inherits `CamelModel`,
 * whose `alias_generator=to_camel` renames fields on serialisation, so the wire carries
 * `transitionedAt` and `lockedAt`. Reading `transitioned_at` / `locked_at` does not fail loudly —
 * the fields are simply `undefined`, so a locked cohort renders as unlocked and a phase that
 * transitioned months ago renders as "never transitioned". A page that quietly misreports the
 * study's own state is the exact failure this page was rewritten to end.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const useStudyGroups = vi.fn();
const useStudyPhase = vi.fn();
vi.mock("@/hooks/use-study", () => ({
  useStudyGroups: () => useStudyGroups(),
  useStudyPhase: () => useStudyPhase(),
  // The page now also renders the allocation, phase and audit panels the console used to point
  // at but not provide. A module mock replaces the WHOLE module, so every export those panels
  // reach for has to be present here — an unmocked one comes back undefined and the component
  // throws while rendering, which is what these three lines are for.
  useAssignGroup: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useLockAssignments: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSetPhase: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePhaseHistory: () => ({ data: [], isPending: false, isError: false }),
  useStudyAudit: () => ({ data: [], isPending: false, isError: false }),
}));

// The allocation table lists learner accounts to assign. These tests are about the allocation
// SUMMARY the page has always shown, so the roster read returns empty rather than fixtures.
vi.mock("@/hooks/use-admin-users", () => ({
  useAdminUsers: () => ({
    data: { items: [], total: 0, page: 1, pageSize: 100 },
    isPending: false,
    isError: false,
  }),
}));

import ABGroupsPage from "./page";

function groups(items: Array<Record<string, unknown>>) {
  return { data: { items, total: items.length, page: 1, pageSize: 100 }, isLoading: false, isError: false };
}

describe("A/B groups page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useStudyPhase.mockReturnValue({
      data: { phase: "phase_a", transitionedAt: null },
      isLoading: false,
      isError: false,
    });
    useStudyGroups.mockReturnValue(groups([]));
  });

  it("reads lockedAt from the wire, not locked_at", () => {
    // With the snake_case spelling these count as unlocked and the page urges you to lock
    // assignments that are already locked.
    useStudyGroups.mockReturnValue(
      groups([
        { userId: "u1", group: "adaptive", lockedAt: "2026-08-24T11:04:44Z" },
        { userId: "u2", group: "control", lockedAt: "2026-08-24T11:04:44Z" },
      ]),
    );

    render(<ABGroupsPage />);

    expect(screen.getByText(/2 assigned · 2 locked/)).toBeInTheDocument();
    expect(
      screen.queryByText(/Assignments are unlocked/),
    ).not.toBeInTheDocument();
  });

  it("warns while assignments are still unlocked", () => {
    useStudyGroups.mockReturnValue(
      groups([{ userId: "u1", group: "adaptive", lockedAt: null }]),
    );

    render(<ABGroupsPage />);

    expect(screen.getByText(/Assignments are unlocked/)).toBeInTheDocument();
  });

  it("reads transitionedAt from the wire, not transitioned_at", () => {
    useStudyPhase.mockReturnValue({
      data: { phase: "phase_b", transitionedAt: "2026-08-24T11:04:44.098915Z" },
      isLoading: false,
      isError: false,
    });

    render(<ABGroupsPage />);

    expect(screen.queryByText(/never transitioned/)).not.toBeInTheDocument();
  });

  it("counts each real condition separately", () => {
    useStudyGroups.mockReturnValue(
      groups([
        { userId: "u1", group: "adaptive", lockedAt: null },
        { userId: "u2", group: "adaptive", lockedAt: null },
        { userId: "u3", group: "control", lockedAt: null },
      ]),
    );

    render(<ABGroupsPage />);

    // The per-condition counts, which is what the page exists to report. `control` appears more
    // than once as text (the chip, and the note that unassigned accounts default to it), so the
    // counts are the unambiguous assertion.
    expect(screen.getByText("2")).toBeInTheDocument();   // adaptive
    expect(screen.getByText("1")).toBeInTheDocument();   // control
    expect(screen.getByText(/3 assigned/)).toBeInTheDocument();
  });

  it("says no learner is adapted in phase_a, whatever the group counts say", () => {
    // The counts alone read as "these people are receiving interventions". In phase_a nobody is.
    render(<ABGroupsPage />);
    expect(
      screen.getByText(/no learner receives interventions in phase_a/),
    ).toBeInTheDocument();
  });

  it("states that assignment is manual rather than a randomisation algorithm", () => {
    render(<ABGroupsPage />);
    // Said in more than one place now that the allocation controls are on the page: the summary
    // explains it and the control that performs it repeats it. `getAllByText` because a single
    // match is no longer the property being asserted — the absence of the false claim below is.
    expect(screen.getAllByText(/manual/).length).toBeGreaterThan(0);
    expect(
      screen.queryByText(/balanced randomization algorithm/i),
    ).not.toBeInTheDocument();
  });
});
