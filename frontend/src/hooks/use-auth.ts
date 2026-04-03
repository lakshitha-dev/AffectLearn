"use client";

import { useCallback } from "react";
import { apiFetch, ApiRequestError } from "@/lib/api-client";
import { useSessionStore } from "@/stores/session-store";
import type { TokenResponse, UserResponse } from "@/types/api-responses";

interface RegisterData {
  emailAddress: string;
  password: string;
  firstName: string;
  lastName: string;
  ageRange?: string;
  degreeProgram?: string;
}

interface LoginData {
  emailAddress: string;
  password: string;
}

export function useAuth() {
  const { setTokens, setUser, clearSession, user, accessToken, expiresAt } =
    useSessionStore();

  const isAuthenticated = accessToken !== null && expiresAt !== null && Date.now() < expiresAt;

  const fetchUser = useCallback(async () => {
    try {
      const userData = await apiFetch<UserResponse>("/auth/me");
      setUser(userData);
      return userData;
    } catch {
      return null;
    }
  }, [setUser]);

  const register = useCallback(
    async (data: RegisterData) => {
      const tokens = await apiFetch<TokenResponse>("/auth/register", {
        method: "POST",
        body: JSON.stringify(data),
      });
      setTokens(tokens.accessToken, tokens.refreshToken, tokens.expiresIn);
      const userData = await apiFetch<UserResponse>("/auth/me");
      setUser(userData);
      return userData;
    },
    [setTokens, setUser],
  );

  const login = useCallback(
    async (data: LoginData) => {
      const tokens = await apiFetch<TokenResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify(data),
      });
      setTokens(tokens.accessToken, tokens.refreshToken, tokens.expiresIn);
      const userData = await apiFetch<UserResponse>("/auth/me");
      setUser(userData);
      return userData;
    },
    [setTokens, setUser],
  );

  const logout = useCallback(() => {
    clearSession();
  }, [clearSession]);

  const refreshToken = useCallback(async () => {
    const rt = useSessionStore.getState().refreshToken;
    if (!rt) return false;
    try {
      const tokens = await apiFetch<TokenResponse>("/auth/refresh", {
        method: "POST",
        body: JSON.stringify({ refreshToken: rt }),
      });
      setTokens(tokens.accessToken, tokens.refreshToken, tokens.expiresIn);
      return true;
    } catch {
      clearSession();
      return false;
    }
  }, [setTokens, clearSession]);

  return {
    user,
    isAuthenticated,
    register,
    login,
    logout,
    refreshToken,
    fetchUser,
  };
}
