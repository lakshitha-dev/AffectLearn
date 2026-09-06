"use client";

/**
 * Query hooks for the study-administration endpoints.
 *
 * These back the A/B groups page, which until now rendered a hardcoded array: three conditions
 * that do not exist in the system (`webcam`, `behavioral`) and invented member counts. Reading
 * the real endpoints is the whole point — a research console that displays fabricated allocation
 * is worse than one that displays nothing, because it will be believed.
 */

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";

export const STUDY_KEY = "study";

/** The two real conditions. Mirrors `GROUPS` in backend/app/agents/state.py. */
export type StudyGroupName = "adaptive" | "control";

/**
 * Field names are camelCase because that is what the wire carries: every REST response model
 * inherits `CamelModel`, whose `alias_generator=to_camel` renames fields on serialisation. Typing
 * these in snake_case does not fail loudly — the fields simply read `undefined`, so a lock shows
 * as unlocked and a transition shows as "never". Verified against the live API.
 */
export interface GroupAssignment {
  userId: string;
  group: StudyGroupName | string;
  lockedAt: string | null;
  createdAt?: string;
}

export interface GroupAssignmentPage {
  items: GroupAssignment[];
  total: number;
  page: number;
  pageSize: number;
}

export interface PhaseState {
  phase: string;
  transitionedAt: string | null;
}

/** Every recorded assignment. Paginated server-side; the page size here covers a pilot cohort. */
export function useStudyGroups(pageSize = 100) {
  return useQuery<GroupAssignmentPage>({
    queryKey: [STUDY_KEY, "groups", pageSize],
    queryFn: () => apiFetch<GroupAssignmentPage>(`/admin/study/groups?page_size=${pageSize}`),
    staleTime: 30_000,
  });
}

/**
 * The global study phase.
 *
 * Phase is a SINGLETON, not a per-learner attribute: `phase_a` collects non-adaptive data for
 * everyone, `phase_b` turns the adaptive branch on for the adaptive group only. Eligibility for
 * an intervention is exactly `phase_b AND adaptive`, so this value decides whether any learner
 * can receive one at all.
 */
export function useStudyPhase() {
  return useQuery<PhaseState>({
    queryKey: [STUDY_KEY, "phase"],
    queryFn: () => apiFetch<PhaseState>("/admin/study/phase"),
    staleTime: 30_000,
  });
}
