/**
 * Tests for the session store.
 *
 * Every other store had tests and this one — which decides whether anybody is signed in, holds
 * the tokens, and gates every guarded route — had none.
 *
 * Three properties matter enough to pin. Expiry must be evaluated against the clock rather than
 * assumed from a token's presence, or an expired session keeps rendering the app until the first
 * API call fails. `hasHydrated` must be a distinct third state from "signed in" and "signed out",
 * because guards that cannot tell "not loaded yet" from "not signed in" bounce users between
 * /login and their dashboard. And `partialize` must not persist it, or a reload restores
 * `hasHydrated: true` before rehydration has actually happened.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";

import { useSessionStore } from "./session-store";
import type { UserResponse } from "@/types/api-responses";

const USER: UserResponse = {
  id: "u1",
  emailAddress: "learner@test.com",
  firstName: "Test",
  lastName: "Learner",
  role: "learner",
};

const HOUR = 60 * 60;

function reset() {
  useSessionStore.setState({
    accessToken: null,
    refreshToken: null,
    expiresAt: null,
    user: null,
    hasHydrated: false,
  });
}

beforeEach(reset);
afterEach(() => vi.useRealTimers());

describe("setTokens", () => {
  it("stores tokens and converts expiresIn seconds to an absolute deadline", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));

    useSessionStore.getState().setTokens("access", "refresh", HOUR);

    const state = useSessionStore.getState();
    expect(state.accessToken).toBe("access");
    expect(state.refreshToken).toBe("refresh");
    expect(state.expiresAt).toBe(Date.now() + HOUR * 1000);
  });
});

describe("isAuthenticated", () => {
  it("is false with no token", () => {
    expect(useSessionStore.getState().isAuthenticated()).toBe(false);
  });

  it("is true for an unexpired token", () => {
    useSessionStore.getState().setTokens("access", "refresh", HOUR);
    expect(useSessionStore.getState().isAuthenticated()).toBe(true);
  });

  it("is false once the deadline has passed, even though the token is still stored", () => {
    // The failure this guards: treating "a token exists" as "signed in" keeps rendering the app
    // for an expired session until the first API call comes back 401.
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
    useSessionStore.getState().setTokens("access", "refresh", HOUR);

    vi.setSystemTime(new Date("2026-01-01T01:00:01Z"));

    expect(useSessionStore.getState().accessToken).toBe("access");
    expect(useSessionStore.getState().isAuthenticated()).toBe(false);
  });
});

describe("shouldRefresh", () => {
  it("is false with no session", () => {
    expect(useSessionStore.getState().shouldRefresh()).toBe(false);
  });

  it("is false well before expiry", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
    useSessionStore.getState().setTokens("access", "refresh", HOUR);

    expect(useSessionStore.getState().shouldRefresh()).toBe(false);
  });

  it("is true inside the five-minute lead", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
    useSessionStore.getState().setTokens("access", "refresh", HOUR);

    // 56 minutes in: four minutes left, inside the lead.
    vi.setSystemTime(new Date("2026-01-01T00:56:00Z"));

    expect(useSessionStore.getState().shouldRefresh()).toBe(true);
  });

  it("is false without a refresh token, however close expiry is", () => {
    // Nothing to refresh WITH — returning true would loop a refresh that cannot succeed.
    useSessionStore.setState({
      accessToken: "access",
      refreshToken: null,
      expiresAt: Date.now() + 1_000,
    });

    expect(useSessionStore.getState().shouldRefresh()).toBe(false);
  });
});

describe("clearSession", () => {
  it("removes tokens and the user", () => {
    useSessionStore.getState().setTokens("access", "refresh", HOUR);
    useSessionStore.getState().setUser(USER);

    useSessionStore.getState().clearSession();

    const state = useSessionStore.getState();
    expect(state.accessToken).toBeNull();
    expect(state.refreshToken).toBeNull();
    expect(state.expiresAt).toBeNull();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated()).toBe(false);
  });

  it("leaves hasHydrated alone", () => {
    // Signing out does not un-load the store. Resetting it here would put guards back into the
    // "still deciding" state and hold a spinner over the login redirect.
    useSessionStore.getState().setHasHydrated(true);

    useSessionStore.getState().clearSession();

    expect(useSessionStore.getState().hasHydrated).toBe(true);
  });
});

describe("persistence", () => {
  it("does not persist hasHydrated", () => {
    // Persisting it would restore `true` from storage BEFORE rehydration has run, which is
    // exactly the state the flag exists to distinguish.
    const persisted = useSessionStore.persist.getOptions().partialize?.({
      ...useSessionStore.getState(),
      hasHydrated: true,
    });

    expect(persisted).toBeDefined();
    expect(persisted).not.toHaveProperty("hasHydrated");
  });

  it("persists exactly the session fields", () => {
    useSessionStore.getState().setTokens("access", "refresh", HOUR);
    useSessionStore.getState().setUser(USER);

    const persisted = useSessionStore.persist
      .getOptions()
      .partialize?.(useSessionStore.getState()) as Record<string, unknown>;

    expect(Object.keys(persisted).sort()).toEqual(
      ["accessToken", "expiresAt", "refreshToken", "user"].sort()
    );
  });
});
