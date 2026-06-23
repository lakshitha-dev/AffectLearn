"use client";

import { useCallback } from "react";
import { apiFetch } from "@/lib/api-client";
import { useSessionStore } from "@/stores/session-store";
import type {
  MessageResponse,
  TokenResponse,
  UserResponse,
} from "@/types/api-responses";

interface RegisterData {
  emailAddress: string;
  password: string;
  firstName: string;
  lastName: string;
  ageRange?: string;
  degreeProgram?: string;
  designerInviteCode?: string;
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

  // Registration no longer logs the user in — the account must verify its email first.
  // Returns the server's confirmation message.
  const register = useCallback(async (data: RegisterData) => {
    return apiFetch<MessageResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }, []);

  // Confirm an email-verification token; the backend auto-logs-in on success.
  const verifyEmail = useCallback(
    async (token: string) => {
      const tokens = await apiFetch<TokenResponse>("/auth/verify-email", {
        method: "POST",
        body: JSON.stringify({ token }),
      });
      setTokens(tokens.accessToken, tokens.refreshToken, tokens.expiresIn);
      const userData = await apiFetch<UserResponse>("/auth/me");
      setUser(userData);
      return userData;
    },
    [setTokens, setUser],
  );

  const resendVerification = useCallback(async (emailAddress: string) => {
    return apiFetch<MessageResponse>("/auth/resend-verification", {
      method: "POST",
      body: JSON.stringify({ emailAddress }),
    });
  }, []);

  const forgotPassword = useCallback(async (emailAddress: string) => {
    return apiFetch<MessageResponse>("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ emailAddress }),
    });
  }, []);

  const resetPassword = useCallback(
    async (token: string, password: string) => {
      return apiFetch<MessageResponse>("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, password }),
      });
    },
    [],
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
    verifyEmail,
    resendVerification,
    forgotPassword,
    resetPassword,
  };
}
