/**
 * Tests for the section-detail page (Story 7.4, AC1/AC3/AC7/AC8/AC9).
 *
 * Covers: the three panels render for data; key-insights renders both fields +
 * null fallbacks and does NOT render hints/breaks; skeleton (role=status) shows
 * while pending with NO spinner; error + Retry path; the "Edit Content" link →
 * `/content-editor`; the back link → `/analytics/{courseId}`; the "Limited data"
 * badge shows when `insufficientData`. `useSectionDetail`, `useParams`, and
 * `next/link` are mocked.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { createElement } from "react";

import type { SectionDetailResponse } from "@/types/analytics";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
  }) => createElement("a", { href, ...rest }, children),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ courseId: "course-1", sectionId: "sec-1" }),
}));

vi.mock("@/hooks/use-analytics", () => ({
  useSectionDetail: vi.fn(),
  // The page now also renders the per-question item-analysis panel, so its hook has to be
  // mocked here too — a module mock replaces the WHOLE module and an unmocked export comes back
  // undefined rather than falling through to the real one.
  //
  // Returns empty, not fixtures: these tests are about the three affect panels, and the item
  // table's own behaviour belongs with the component.
  useSectionQuestions: vi.fn(() => ({
    data: { sectionId: "sec-1", questions: [] },
    isPending: false,
    isError: false,
  })),
}));

import { useSectionDetail } from "@/hooks/use-analytics";
import SectionDetailPage from "./page";

const mockUseSectionDetail = useSectionDetail as unknown as ReturnType<
  typeof vi.fn
>;

const detail: SectionDetailResponse = {
  sectionId: "sec-1",
  sectionTitle: "Subnetting Deep Dive",
  affectDistribution: {
    engagedPct: 40,
    confusedPct: 68,
    boredPct: 10,
    frustratedPct: 12,
  },
  temporalDistribution: [{ binIndex: 0, confusedPct: 50 }],
  keyInsights: {
    mostTriggeredAdaptationType: "hint",
    averageConfusionDurationSeconds: 63,
  },
  content: [
    {
      blockId: "b1",
      paragraphIndex: 0,
      blockType: "text",
      text: "Subnet masks confuse learners.",
      affectDistribution: {
        engagedPct: 40,
        confusedPct: 68,
        boredPct: 10,
        frustratedPct: 12,
      },
    },
  ],
  sampleCount: 80,
  confidence: "high",
  insufficientData: false,
};

function queryResult(over: Record<string, unknown> = {}) {
  return {
    data: detail,
    isPending: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

describe("SectionDetailPage", () => {
  beforeEach(() => {
    mockUseSectionDetail.mockReset();
  });

  it("renders the three panels for loaded data", () => {
    mockUseSectionDetail.mockReturnValue(queryResult());
    render(<SectionDetailPage />);

    expect(
      screen.getByRole("heading", { name: "Subnetting Deep Dive" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Affect Distribution")).toBeInTheDocument();
    expect(screen.getByText("Key Insights")).toBeInTheDocument();
    expect(screen.getByText("Content Preview")).toBeInTheDocument();
  });

  it("renders both key-insight fields and NOT hints/breaks", () => {
    mockUseSectionDetail.mockReturnValue(queryResult());
    render(<SectionDetailPage />);

    expect(screen.getByText("Most-Triggered Adaptation")).toBeInTheDocument();
    expect(screen.getByText("hint")).toBeInTheDocument();
    expect(screen.getByText("Average Confusion Duration")).toBeInTheDocument();
    // 63s → "1m 03s".
    expect(screen.getByText("1m 03s")).toBeInTheDocument();

    expect(screen.queryByText(/needed hints/i)).toBeNull();
    expect(screen.queryByText(/took breaks/i)).toBeNull();
  });

  it("renders graceful fallbacks for null key insights", () => {
    mockUseSectionDetail.mockReturnValue(
      queryResult({
        data: {
          ...detail,
          keyInsights: {
            mostTriggeredAdaptationType: null,
            averageConfusionDurationSeconds: null,
          },
        },
      }),
    );
    render(<SectionDetailPage />);

    expect(screen.getByText("None")).toBeInTheDocument();
    expect(screen.getByText("No adaptations triggered")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("shows a skeleton (role=status) and NO spinner while pending", () => {
    mockUseSectionDetail.mockReturnValue(
      queryResult({ data: undefined, isPending: true }),
    );
    const { container } = render(<SectionDetailPage />);

    expect(
      screen.getByRole("status", { name: "Loading section detail" }),
    ).toBeInTheDocument();
    expect(container.querySelector(".animate-spin")).toBeNull();
    expect(container.querySelector('[role="progressbar"]')).toBeNull();
  });

  it("shows an inline error message + Retry on fetch error", () => {
    mockUseSectionDetail.mockReturnValue(
      queryResult({ data: undefined, isError: true, error: new Error("boom") }),
    );
    render(<SectionDetailPage />);

    const region = screen.getByText(
      "Couldn't load the section detail",
    ).parentElement!;
    expect(
      within(region).getByRole("button", { name: /Retry/ }),
    ).toBeInTheDocument();
    expect(within(region).getByText("boom")).toBeInTheDocument();
  });

  it("links 'Edit Content' to the editor index and 'Back to heatmap' to the course", () => {
    mockUseSectionDetail.mockReturnValue(queryResult());
    render(<SectionDetailPage />);

    expect(
      screen.getByRole("link", { name: "Edit Content" }),
    ).toHaveAttribute("href", "/content-editor");
    expect(
      screen.getByRole("link", { name: /Back to heatmap/ }),
    ).toHaveAttribute("href", "/analytics/course-1");
  });

  it("shows the 'Limited data' badge when insufficientData", () => {
    mockUseSectionDetail.mockReturnValue(
      queryResult({ data: { ...detail, insufficientData: true } }),
    );
    render(<SectionDetailPage />);
    expect(screen.getByText("Limited data")).toBeInTheDocument();
  });
});
