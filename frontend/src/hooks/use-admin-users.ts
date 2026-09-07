import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";

export type UserRole = "learner" | "course_designer" | "admin";

export interface AdminUser {
  id: string;
  emailAddress: string;
  firstName: string;
  lastName: string;
  role: UserRole;
  isActive: boolean;
  emailVerified: boolean;
  createdAt: string | null;
}

export interface PaginatedUsers {
  items: AdminUser[];
  total: number;
  page: number;
  pageSize: number;
}

export interface UserFilters {
  page: number;
  pageSize: number;
  search?: string;
  role?: UserRole | "";
  isActive?: boolean | null;
}

const KEY = "adminUsers";

/**
 * Server-side listing.
 *
 * The console used to fetch one hardcoded page of 100 and filter it in the browser, which stops
 * working at the 101st account — the pilot's own recruitment target is inside that margin, and
 * the failure is silent: the table simply stops mentioning people.
 */
export function useAdminUsers(filters: UserFilters) {
  const params = new URLSearchParams({
    page: String(filters.page),
    page_size: String(filters.pageSize),
  });
  if (filters.search) params.set("search", filters.search);
  if (filters.role) params.set("role", filters.role);
  if (filters.isActive != null) params.set("is_active", String(filters.isActive));

  return useQuery<PaginatedUsers>({
    queryKey: [KEY, filters],
    queryFn: () => apiFetch<PaginatedUsers>(`/admin/users?${params.toString()}`),
  });
}

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: [KEY] });
}

export function useUpdateUser() {
  const invalidate = useInvalidate();
  return useMutation<
    AdminUser,
    Error,
    { userId: string; role?: UserRole; isActive?: boolean }
  >({
    mutationFn: ({ userId, ...patch }) =>
      apiFetch<AdminUser>(`/admin/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
    onSuccess: invalidate,
  });
}

export interface ErasureReceipt {
  deleted: Record<string, number>;
}

/**
 * Withdraw a participant and erase their data (Story 8.7 / FR49).
 *
 * Delegates to the same erasure the learner's own delete button uses, so both paths remove
 * exactly the same rows. The receipt is the evidence a study needs that it happened.
 */
export function useWithdrawParticipant() {
  const invalidate = useInvalidate();
  return useMutation<ErasureReceipt, Error, { userId: string }>({
    mutationFn: ({ userId }) =>
      apiFetch<ErasureReceipt>(`/admin/users/${userId}/withdraw`, { method: "POST" }),
    onSuccess: invalidate,
  });
}
