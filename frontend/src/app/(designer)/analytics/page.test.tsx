/**
 * Tests for the analytics landing page.
 *
 * This page used to call no API and render a permanent "No affect data yet" state — the first
 * screen a designer sees after signing in said the same thing whether or not data existed. These
 * pin the two things that make it real: it lists courses, and it lists only the ones whose
 * analytics the caller may actually open.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { createElement } from "react";

import type { Course } from "@/types/course";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) =>
    createElement("a", { href, ...rest }, children),
}));

const useCourses = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-courses", () => ({ useCourses }));

// CourseRow fetches its own per-course overview; stub it so these tests are about the list.
vi.mock("@/hooks/use-analytics", () => ({
  useCourseOverview: () => ({ data: undefined, isPending: true, isError: false }),
}));

import AnalyticsIndexPage from "./page";

function course(overrides: Partial<Course>): Course {
  return {
    id: "c1",
    title: "A Course",
    description: null,
    estimatedDurationMinutes: null,
    isPublished: true,
    createdAt: "",
    updatedAt: "",
    ...overrides,
  } as Course;
}

beforeEach(() => useCourses.mockReset());

describe("analytics landing", () => {
  it("lists the designer's own courses", () => {
    useCourses.mockReturnValue({
      data: { items: [course({ id: "c1", title: "Networking", canEdit: true, createdBy: "me" })] },
      isPending: false,
      isError: false,
    });

    render(createElement(AnalyticsIndexPage));

    expect(screen.getByText("Networking")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/analytics/c1");
  });

  it("includes seeded system content, which is what the pilot runs on", () => {
    useCourses.mockReturnValue({
      data: {
        items: [course({ id: "sys", title: "Pilot Course", canEdit: false, createdBy: null })],
      },
      isPending: false,
      isError: false,
    });

    render(createElement(AnalyticsIndexPage));

    expect(screen.getByText("Pilot Course")).toBeInTheDocument();
  });

  it("hides another designer's course rather than linking to a 403", () => {
    useCourses.mockReturnValue({
      data: {
        items: [course({ id: "theirs", title: "Someone Else's", canEdit: false, createdBy: "u2" })],
      },
      isPending: false,
      isError: false,
    });

    render(createElement(AnalyticsIndexPage));

    expect(screen.queryByText("Someone Else's")).not.toBeInTheDocument();
    expect(screen.getByText("No courses to analyse yet")).toBeInTheDocument();
  });

  it("shows an empty state when there are no courses at all", () => {
    useCourses.mockReturnValue({ data: { items: [] }, isPending: false, isError: false });

    render(createElement(AnalyticsIndexPage));

    expect(screen.getByText("No courses to analyse yet")).toBeInTheDocument();
  });

  it("surfaces a load failure with a retry", () => {
    useCourses.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: new Error("boom"),
      refetch: vi.fn(),
    });

    render(createElement(AnalyticsIndexPage));

    expect(screen.getByText("Couldn't load your courses")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
