import { useMutation } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";
import { useSessionStore } from "@/stores/session-store";
import type { MessageResponse, UserResponse } from "@/types/api-responses";

export interface ProfileUpdate {
  firstName?: string;
  lastName?: string;
  ageRange?: string | null;
  degreeProgram?: string | null;
}

/**
 * Update the signed-in account's own profile.
 *
 * Writes the response straight back into the session store, because the user object there is what
 * renders the top bar, the profile header and the avatar initials — leaving it stale would show a
 * saved name everywhere except the places that display it.
 */
export function useUpdateProfile() {
  const setUser = useSessionStore((s) => s.setUser);

  return useMutation<UserResponse, Error, ProfileUpdate>({
    mutationFn: (body) =>
      apiFetch<UserResponse>("/auth/me", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: (updated) => setUser(updated),
  });
}

export interface PasswordChange {
  currentPassword: string;
  newPassword: string;
}

/**
 * Change the signed-in account's password.
 *
 * The endpoint has existed since the auth epic; nothing in any role's UI ever called it, so the
 * only route to a new password was the signed-out "forgot password" email flow.
 */
export function useChangePassword() {
  return useMutation<MessageResponse, Error, PasswordChange>({
    mutationFn: (body) =>
      apiFetch<MessageResponse>("/auth/change-password", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}
