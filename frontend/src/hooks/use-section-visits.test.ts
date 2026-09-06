/**
 * Tests for the section-visit log (migration 022).
 *
 * `section_progress` records one completion per section, so a learner who reads a section,
 * moves on, comes back confused and re-reads it leaves the same row as one who read it once.
 * These cover the behaviour that makes revisits visible, and the failure posture that keeps
 * instrumentation from ever interrupting a learner.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

vi.mock("@/lib/api-client", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api-client";
import { useSectionVisits } from "./use-section-visits";

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

const SECTION_A = "sec-a";
const SECTION_B = "sec-b";

function callsTo(path: string) {
  return mockApiFetch.mock.calls.filter(([url]) => String(url) === path);
}

function bodyOf(call: unknown[]): Record<string, unknown> {
  return JSON.parse(String((call[1] as { body: string }).body));
}

beforeEach(() => {
  mockApiFetch.mockReset();
  let n = 0;
  mockApiFetch.mockImplementation((url: string) => {
    if (url === "/section-visits") {
      n += 1;
      return Promise.resolve({ id: `visit-${n}`, sectionId: "x" });
    }
    return Promise.resolve({});
  });
});

describe("useSectionVisits", () => {
  it("opens a visit when the learner lands on a section", async () => {
    renderHook(() => useSectionVisits(SECTION_A));

    await waitFor(() => expect(callsTo("/section-visits")).toHaveLength(1));
    expect(bodyOf(callsTo("/section-visits")[0]).sectionId).toBe(SECTION_A);
  });

  it("labels the first section of a page load as a direct arrival", async () => {
    // It is either a fresh start or a resume, and the two cannot be told apart from here.
    renderHook(() => useSectionVisits(SECTION_A));

    await waitFor(() => expect(callsTo("/section-visits")).toHaveLength(1));
    expect(bodyOf(callsTo("/section-visits")[0]).entrySource).toBe("direct");
  });

  it("closes the previous visit when the learner moves on", async () => {
    const { rerender } = renderHook(({ id }) => useSectionVisits(id), {
      initialProps: { id: SECTION_A },
    });
    await waitFor(() => expect(callsTo("/section-visits")).toHaveLength(1));

    rerender({ id: SECTION_B });

    await waitFor(() =>
      expect(callsTo("/section-visits/visit-1/close")).toHaveLength(1),
    );
  });

  it("records a second visit when the learner returns to the same section", async () => {
    // The whole point: `section_progress` would show one completion for both.
    const { rerender } = renderHook(({ id }) => useSectionVisits(id), {
      initialProps: { id: SECTION_A },
    });
    await waitFor(() => expect(callsTo("/section-visits")).toHaveLength(1));

    rerender({ id: SECTION_B });
    await waitFor(() => expect(callsTo("/section-visits")).toHaveLength(2));
    rerender({ id: SECTION_A });

    await waitFor(() => expect(callsTo("/section-visits")).toHaveLength(3));
    expect(bodyOf(callsTo("/section-visits")[2]).sectionId).toBe(SECTION_A);
  });

  it("carries the entry source the navigation handler set", async () => {
    const { result, rerender } = renderHook(({ id }) => useSectionVisits(id), {
      initialProps: { id: SECTION_A },
    });
    await waitFor(() => expect(callsTo("/section-visits")).toHaveLength(1));

    act(() => result.current.setEntrySource("back"));
    rerender({ id: SECTION_B });

    await waitFor(() => expect(callsTo("/section-visits")).toHaveLength(2));
    expect(bodyOf(callsTo("/section-visits")[1]).entrySource).toBe("back");
  });

  it("defaults later moves to forward rather than reusing the first arrival", async () => {
    const { rerender } = renderHook(({ id }) => useSectionVisits(id), {
      initialProps: { id: SECTION_A },
    });
    await waitFor(() => expect(callsTo("/section-visits")).toHaveLength(1));

    rerender({ id: SECTION_B });

    await waitFor(() => expect(callsTo("/section-visits")).toHaveLength(2));
    expect(bodyOf(callsTo("/section-visits")[1]).entrySource).toBe("next");
  });

  it("reports a duration when closing", async () => {
    const { rerender } = renderHook(({ id }) => useSectionVisits(id), {
      initialProps: { id: SECTION_A },
    });
    await waitFor(() => expect(callsTo("/section-visits")).toHaveLength(1));

    rerender({ id: SECTION_B });

    await waitFor(() =>
      expect(callsTo("/section-visits/visit-1/close")).toHaveLength(1),
    );
    const body = bodyOf(callsTo("/section-visits/visit-1/close")[0]);
    expect(typeof body.durationSeconds).toBe("number");
    expect(body.durationSeconds as number).toBeGreaterThanOrEqual(0);
  });

  it("swallows a failure to open — a lost row must never cost a lesson", async () => {
    mockApiFetch.mockRejectedValue(new Error("network down"));

    const { rerender } = renderHook(({ id }) => useSectionVisits(id), {
      initialProps: { id: SECTION_A },
    });
    await waitFor(() => expect(callsTo("/section-visits")).toHaveLength(1));

    // Navigating on after a failed open must not throw, and must not try to close a visit that
    // was never opened.
    expect(() => rerender({ id: SECTION_B })).not.toThrow();
  });

  it("does nothing without a section", () => {
    renderHook(() => useSectionVisits(undefined));
    expect(mockApiFetch).not.toHaveBeenCalled();
  });
});
