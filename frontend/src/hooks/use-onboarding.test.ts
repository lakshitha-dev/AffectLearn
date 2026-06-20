/**
 * Tests for the onboarding hooks (Story 6.3).
 *
 * Covers AC7: "submit → API call + navigation to /courses" — verifies that
 * useSubmitQuestionnaire posts responses to the correct endpoint via apiFetch.
 * Navigation to /courses is orchestrated by page.tsx (outside this hook's scope).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";

// ---------------------------------------------------------------------------
// Mock apiFetch so no real network call is made.
// ---------------------------------------------------------------------------
vi.mock("@/lib/api-client", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api-client";
import { useSubmitQuestionnaire } from "./use-onboarding";

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

const VALID_RESPONSES = {
  Q1: "21-23",
  Q2: "female",
  Q3: "several_per_week",
  Q4: "3-5",
  Q5: "1-2",
  Q6: "4",
  Q7: "video",
  Q8: { boredom: "2", confusion: "3", frustration: "2", engagement: "4" },
  Q9: ["take_break"],
  Q10: "yes_once_twice",
  Q11: "5",
  Q12: "4",
  Q13: "4",
  Q14: "3",
};

describe("useSubmitQuestionnaire (AC7 — submit → API call)", () => {
  beforeEach(() => {
    mockApiFetch.mockReset();
    mockApiFetch.mockResolvedValue({ id: "abc", userId: "u1", responses: VALID_RESPONSES, submittedAt: "2026-01-01T00:00:00Z" });
  });

  it("posts responses to /onboarding/questionnaire with the correct shape", async () => {
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useSubmitQuestionnaire(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(VALID_RESPONSES as Record<string, unknown>);
    });

    expect(mockApiFetch).toHaveBeenCalledTimes(1);
    const [path, opts] = mockApiFetch.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/onboarding/questionnaire");
    expect(opts.method).toBe("POST");
    const body = JSON.parse(opts.body as string) as { responses: unknown };
    expect(body.responses).toEqual(VALID_RESPONSES);
  });

  it("mutateAsync resolves with the API response on success", async () => {
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useSubmitQuestionnaire(), { wrapper });

    let returnValue: unknown;
    await act(async () => {
      returnValue = await result.current.mutateAsync(VALID_RESPONSES as Record<string, unknown>);
    });

    // The hook resolves with whatever apiFetch returned.
    expect(returnValue).toMatchObject({ id: "abc" });
    // And the API was called exactly once.
    expect(mockApiFetch).toHaveBeenCalledTimes(1);
  });

  it("mutation is in error state when apiFetch rejects", async () => {
    mockApiFetch.mockRejectedValue(new Error("network error"));
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useSubmitQuestionnaire(), { wrapper });

    await act(async () => {
      try {
        await result.current.mutateAsync(VALID_RESPONSES as Record<string, unknown>);
      } catch {
        // expected
      }
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
