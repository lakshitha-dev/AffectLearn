import { useSessionStore } from "@/stores/session-store";
import type { TokenResponse } from "@/types/api-responses";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

let isRefreshing = false;
let refreshPromise: Promise<string | null> | null = null;

export async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken, setTokens, clearSession } = useSessionStore.getState();
  if (!refreshToken) return null;

  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refreshToken }),
    });

    if (!res.ok) {
      clearSession();
      return null;
    }

    const data: TokenResponse = await res.json();
    setTokens(data.accessToken, data.refreshToken, data.expiresIn);
    return data.accessToken;
  } catch {
    clearSession();
    return null;
  }
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const store = useSessionStore.getState();
  let { accessToken } = store;

  // Auto-refresh if token is about to expire
  if (store.shouldRefresh() && !isRefreshing) {
    isRefreshing = true;
    refreshPromise = refreshAccessToken();
    const newToken = await refreshPromise;
    isRefreshing = false;
    refreshPromise = null;
    if (newToken) accessToken = newToken;
  } else if (isRefreshing && refreshPromise) {
    const newToken = await refreshPromise;
    if (newToken) accessToken = newToken;
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  // Handle 401 by attempting token refresh
  if (res.status === 401 && store.refreshToken && !isRefreshing) {
    isRefreshing = true;
    refreshPromise = refreshAccessToken();
    const newToken = await refreshPromise;
    isRefreshing = false;
    refreshPromise = null;

    if (newToken) {
      headers["Authorization"] = `Bearer ${newToken}`;
      const retryRes = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers,
      });
      if (!retryRes.ok) {
        const errorData = await retryRes.json().catch(() => null);
        throw new ApiRequestError(retryRes.status, errorData);
      }
      return retryRes.json();
    }
  }

  if (!res.ok) {
    const errorData = await res.json().catch(() => null);
    throw new ApiRequestError(res.status, errorData);
  }

  return res.json();
}

/**
 * Download an authenticated file.
 *
 * `apiFetch` always calls `.json()`, so a CSV download needs its own path. This mirrors its token
 * handling -- proactive refresh, plus one retry on a 401 -- so an export never fails for the one
 * reason a long-lived admin page makes likely: an access token that expired while the page sat
 * open. Deliberately a thin duplicate rather than a refactor of `apiFetch`, whose JSON return type
 * is relied on everywhere.
 */
export async function apiFetchBlob(path: string): Promise<Blob> {
  const store = useSessionStore.getState();
  let { accessToken } = store;

  if (store.shouldRefresh() && !isRefreshing) {
    isRefreshing = true;
    refreshPromise = refreshAccessToken();
    const newToken = await refreshPromise;
    isRefreshing = false;
    refreshPromise = null;
    if (newToken) accessToken = newToken;
  } else if (isRefreshing && refreshPromise) {
    const newToken = await refreshPromise;
    if (newToken) accessToken = newToken;
  }

  const headers: Record<string, string> = {};
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  let res = await fetch(`${API_BASE}${path}`, { headers });

  if (res.status === 401 && store.refreshToken && !isRefreshing) {
    isRefreshing = true;
    refreshPromise = refreshAccessToken();
    const newToken = await refreshPromise;
    isRefreshing = false;
    refreshPromise = null;
    if (newToken) {
      headers["Authorization"] = `Bearer ${newToken}`;
      res = await fetch(`${API_BASE}${path}`, { headers });
    }
  }

  if (!res.ok) {
    // An error body here is JSON, not the file.
    const errorData = await res.json().catch(() => null);
    throw new ApiRequestError(res.status, errorData);
  }
  return res.blob();
}

/**
 * Hand a Blob to the user as a file save.
 *
 * The object URL must be revoked or the Blob leaks for the page's lifetime; the anchor has to be
 * in the document for the click to register in Firefox.
 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export class ApiRequestError extends Error {
  constructor(
    public status: number,
    public data: unknown,
  ) {
    const code =
      data && typeof data === "object" && "detail" in data
        ? (data as { detail?: { error?: { message?: string } } }).detail?.error?.message
        : undefined;
    super(code ?? `Request failed with status ${status}`);
    this.name = "ApiRequestError";
  }

  get errorCode(): string | undefined {
    if (this.data && typeof this.data === "object" && "detail" in this.data) {
      return (this.data as { detail?: { error?: { code?: string } } }).detail?.error?.code;
    }
    return undefined;
  }
}
