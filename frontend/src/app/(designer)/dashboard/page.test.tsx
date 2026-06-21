/**
 * Tests for the designer dashboard overview page (Story 7.2, AC2/AC3/AC4).
 *
 * Covers: skeletons (NOT spinners) while loading; stat cards + course rows after
 * resolve; empty state with no courses; course-row click-through target URL.
 * The data hooks are mocked.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";

import type { Course } from "@/types/course";
import type { CourseOverview } from "@/types/analytics";

// --- Mock next/link to a plain anchor so we can assert hrefs ---
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
  }) =>
    // eslint-disable-next-line @next/next/no-html-link-for-pages
    createElement("a", { href, ...rest }, children),
}));

// --- Mock the data hooks ---
vi.mock("@/hooks/use-courses", () => ({
  useCourses: vi.fn(),
}));
vi.mock("@/hooks/use-analytics", () => ({
  useCourseOverview: vi.fn(),
}));

import { createElement } from "react";
import { useCourses } from "@/hooks/use-courses";
import { useCourseOverview } from "@/hooks/use-analytics";
import DesignerDashboardPage from "./page";

const mockUseCourses = useCourses as unknown as ReturnType<typeof vi.fn>;
const mockUseCourseOverview = useCourseOverview as unknown as ReturnType<
  typeof vi.fn
>;

const course: Course = {
  id: "course-1",
  title: "Computer Networking Fundamentals",
  description: null,
  estimatedDurationMinutes: 120,
  isPublished: true,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
};

const overview: CourseOverview = {
  courseId: "course-1",
  totalLearners: 36,
  completionRate: 62,
  averageEngagementScore: 74,
  confusionHotspotCount: 3,
  sampleCount: 240,
  confidence: "high",
  insufficientData: false,
};

function coursesResult(over: Partial<ReturnType<typeof Object>> = {}) {
  return {
    data: { items: [course], total: 1, page: 1, pageSize: 50 },
    isPending: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

function overviewResult(over: Record<string, unknown> = {}) {
  return {
    data: overview,
    isPending: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

describe("DesignerDashboardPage", () => {
  beforeEach(() => {
    mockUseCourses.mockReset();
    mockUseCourseOverview.mockReset();
  });

  it("shows skeletons (role=status) and NO spinner while loading", () => {
    mockUseCourses.mockReturnValue(coursesResult({ data: undefined, isPending: true }));
    mockUseCourseOverview.mockReturnValue(overviewResult({ data: undefined, isPending: true }));

    const { container } = render(<DesignerDashboardPage />);

    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    // Explicit AC: no spinner in the loading path.
    expect(container.querySelector(".animate-spin")).toBeNull();
    expect(container.querySelector('[role="progressbar"]')).toBeNull();
  });

  it("renders stat cards and a course row after data resolves", () => {
    mockUseCourses.mockReturnValue(coursesResult());
    mockUseCourseOverview.mockReturnValue(overviewResult());

    render(<DesignerDashboardPage />);

    expect(screen.getByText("Total Learners")).toBeInTheDocument();
    expect(screen.getByText("Completion Rate")).toBeInTheDocument();
    expect(screen.getByText("Avg Engagement")).toBeInTheDocument();
    expect(screen.getByText("Confusion Hotspots")).toBeInTheDocument();
    // Course row title appears (in the list).
    expect(
      screen.getAllByText("Computer Networking Fundamentals").length,
    ).toBeGreaterThan(0);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("links each course row to its heatmap route /analytics/<courseId>", () => {
    mockUseCourses.mockReturnValue(coursesResult());
    mockUseCourseOverview.mockReturnValue(overviewResult());

    render(<DesignerDashboardPage />);

    const link = screen.getByRole("link", {
      name: /Computer Networking Fundamentals/,
    });
    expect(link).toHaveAttribute("href", "/analytics/course-1");
  });

  it("renders an honest empty state when there are no courses", () => {
    mockUseCourses.mockReturnValue(
      coursesResult({ data: { items: [], total: 0, page: 1, pageSize: 50 } }),
    );
    mockUseCourseOverview.mockReturnValue(overviewResult({ data: undefined }));

    render(<DesignerDashboardPage />);

    expect(screen.getByText("No courses yet")).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("renders a retry affordance when the courses query errors", () => {
    mockUseCourses.mockReturnValue(
      coursesResult({ data: undefined, isError: true, error: new Error("boom") }),
    );
    mockUseCourseOverview.mockReturnValue(overviewResult({ data: undefined }));

    render(<DesignerDashboardPage />);

    const region = screen.getByText("Couldn't load your dashboard").parentElement!;
    expect(within(region).getByRole("button", { name: /Retry/ })).toBeInTheDocument();
  });
});
