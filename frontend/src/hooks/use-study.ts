"use client";

/**
 * Query hooks for the study-administration endpoints.
 *
 * These back the A/B groups page, which until now rendered a hardcoded array: three conditions
 * that do not exist in the system (`webcam`, `behavioral`) and invented member counts. Reading
 * the real endpoints is the whole point — a research console that displays fabricated allocation
 * is worse than one that displays nothing, because it will be believed.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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

/* ------------------------------------------------------------------ */
/* Mutations and integrity reads (Stories 8.2 and 8.4)                 */
/* ------------------------------------------------------------------ */
/*
 * The A/B page was read-only while `admin-settings` told admins to "Change them from A/B Groups",
 * and `POST /admin/study/groups`, `/groups/lock` and `/phase` all existed and were called by
 * nothing. That is a dead loop: the console pointed at a page that could not do the thing.
 */

export interface AuditCheck {
  id: string;
  label: string;
  passed: boolean;
  count: number;
  detail: string;
}

export interface PhaseTransitionEntry {
  fromPhase: string | null;
  toPhase: string | null;
  transitionedAt: string | null;
  timestamp: number;
  actorId: string | null;
  actorName: string | null;
}

function useInvalidateStudy() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: [STUDY_KEY] });
}

export function useAssignGroup() {
  const invalidate = useInvalidateStudy();
  return useMutation<
    GroupAssignment,
    Error,
    { userId: string; group: StudyGroupName }
  >({
    mutationFn: (body) =>
      apiFetch<GroupAssignment>("/admin/study/groups", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: invalidate,
  });
}

/**
 * Lock the cohorts. Irreversible by design — `study_service` raises on any later re-assign, which
 * is the keystone research-integrity guarantee (FR32), so the UI asks first.
 */
export function useLockAssignments() {
  const invalidate = useInvalidateStudy();
  return useMutation<unknown, Error, void>({
    mutationFn: () => apiFetch("/admin/study/groups/lock", { method: "POST" }),
    onSuccess: invalidate,
  });
}

export function useSetPhase() {
  const invalidate = useInvalidateStudy();
  return useMutation<unknown, Error, { phase: string }>({
    mutationFn: (body) =>
      apiFetch("/admin/study/phase", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: invalidate,
  });
}

/** When each phase began, and who began it. Reconstructed from the research event log. */
export function usePhaseHistory() {
  return useQuery<PhaseTransitionEntry[]>({
    queryKey: [STUDY_KEY, "phaseHistory"],
    queryFn: () => apiFetch<PhaseTransitionEntry[]>("/admin/study/phase/history"),
  });
}

/** FR50 research-integrity checks over the A/B assignment. */
export function useStudyAudit() {
  return useQuery<AuditCheck[]>({
    queryKey: [STUDY_KEY, "audit"],
    queryFn: () => apiFetch<AuditCheck[]>("/admin/study/audit"),
  });
}
