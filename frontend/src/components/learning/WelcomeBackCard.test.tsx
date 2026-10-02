import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WelcomeBackCard } from "./WelcomeBackCard";
import type { EnrollmentDetail } from "@/types/enrollment";
import type { ResumeTarget } from "@/types/progress";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/hooks/use-progress", () => ({
  useResumeTarget: vi.fn(),
  buildResumeUrl: vi.fn(),
}));

import { useResumeTarget, buildResumeUrl } from "@/hooks/use-progress";

const mockUseResumeTarget = vi.mocked(useResumeTarget);
const mockBuildResumeUrl = vi.mocked(buildResumeUrl);

const recentDate = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(); // 1 day ago
const oldDate = new Date(Date.now() - 31 * 24 * 60 * 60 * 1000).toISOString(); // 31 days ago

const enrollment: EnrollmentDetail = {
  id: "e1",
  userId: "u1",
  courseId: "c1",
  enrolledAt: "2024-01-01T00:00:00Z",
  progressPercentage: 40,
  lastAccessedAt: recentDate,
  status: "active",
  createdAt: "2024-01-01T00:00:00Z",
  updatedAt: "2024-01-01T00:00:00Z",
  courseTitle: "React Fundamentals",
  courseDescription: "Learn React",
  courseEstimatedDurationMinutes: 300,
  courseModuleCount: 5,
};

const resumeTarget: ResumeTarget = {
  courseId: "c1",
  moduleId: "m1",
  lessonId: "l1",
  sectionId: "s1",
  courseTitle: "React Fundamentals",
  moduleTitle: "Module 1",
  lessonTitle: "Lesson 1",
  sectionTitle: "Introduction to React",
  isLessonComplete: false,
  isCourseComplete: false,
};

describe("WelcomeBackCard", () => {
  let onDismiss: Mock<() => void>;

  beforeEach(() => {
    onDismiss = vi.fn();
    mockBuildResumeUrl.mockReturnValue("/courses/c1/modules/m1/lessons/l1#section-s1");
  });

  describe("returns null conditions", () => {
    it("renders nothing when lastAccessedAt is null", () => {
      mockUseResumeTarget.mockReturnValue({ isLoading: false, data: resumeTarget } as ReturnType<typeof useResumeTarget>);
      const { container } = render(
        <WelcomeBackCard
          enrollment={{ ...enrollment, lastAccessedAt: null }}
          firstName="Lakshitha"
          onDismiss={onDismiss}
        />
      );
      expect(container.firstChild).toBeNull();
    });

    it("renders nothing when lastAccessedAt is older than 30 days", () => {
      mockUseResumeTarget.mockReturnValue({ isLoading: false, data: resumeTarget } as ReturnType<typeof useResumeTarget>);
      const { container } = render(
        <WelcomeBackCard
          enrollment={{ ...enrollment, lastAccessedAt: oldDate }}
          firstName="Lakshitha"
          onDismiss={onDismiss}
        />
      );
      expect(container.firstChild).toBeNull();
    });

    it("renders nothing when resumeQuery.data is null/undefined", () => {
      mockUseResumeTarget.mockReturnValue({ isLoading: false, data: null } as ReturnType<typeof useResumeTarget>);
      const { container } = render(
        <WelcomeBackCard
          enrollment={enrollment}
          firstName="Lakshitha"
          onDismiss={onDismiss}
        />
      );
      expect(container.firstChild).toBeNull();
    });
  });

  describe("loading state", () => {
    it("renders skeleton when resumeQuery is loading", () => {
      mockUseResumeTarget.mockReturnValue({ isLoading: true, data: undefined } as ReturnType<typeof useResumeTarget>);
      const { container } = render(
        <WelcomeBackCard
          enrollment={enrollment}
          firstName="Lakshitha"
          onDismiss={onDismiss}
        />
      );
      // Skeleton renders a div with animate-pulse class
      expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
    });

    it("skeleton is not the main card", () => {
      mockUseResumeTarget.mockReturnValue({ isLoading: true, data: undefined } as ReturnType<typeof useResumeTarget>);
      render(
        <WelcomeBackCard
          enrollment={enrollment}
          firstName="Lakshitha"
          onDismiss={onDismiss}
        />
      );
      expect(screen.queryByText(/Welcome back/)).not.toBeInTheDocument();
    });
  });

  describe("rendered card with firstName", () => {
    beforeEach(() => {
      mockUseResumeTarget.mockReturnValue({ isLoading: false, data: resumeTarget } as ReturnType<typeof useResumeTarget>);
    });

    it("shows personalised heading with firstName", () => {
      render(
        <WelcomeBackCard
          enrollment={enrollment}
          firstName="Lakshitha"
          onDismiss={onDismiss}
        />
      );
      expect(screen.getByRole("heading", { name: "Welcome back, Lakshitha!" })).toBeInTheDocument();
    });

    it("shows generic heading when firstName is null", () => {
      render(
        <WelcomeBackCard
          enrollment={enrollment}
          firstName={null}
          onDismiss={onDismiss}
        />
      );
      expect(screen.getByRole("heading", { name: "Welcome back!" })).toBeInTheDocument();
    });

    it("shows sectionTitle in the card body", () => {
      render(
        <WelcomeBackCard
          enrollment={enrollment}
          firstName="Lakshitha"
          onDismiss={onDismiss}
        />
      );
      expect(screen.getByText("Introduction to React")).toBeInTheDocument();
    });

    it("shows courseTitle in the card body", () => {
      render(
        <WelcomeBackCard
          enrollment={enrollment}
          firstName="Lakshitha"
          onDismiss={onDismiss}
        />
      );
      expect(screen.getByText("React Fundamentals")).toBeInTheDocument();
    });
  });

  describe("dismiss button", () => {
    beforeEach(() => {
      mockUseResumeTarget.mockReturnValue({ isLoading: false, data: resumeTarget } as ReturnType<typeof useResumeTarget>);
    });

    it("renders dismiss button with accessible label", () => {
      render(
        <WelcomeBackCard
          enrollment={enrollment}
          firstName="Lakshitha"
          onDismiss={onDismiss}
        />
      );
      expect(screen.getByRole("button", { name: "Dismiss welcome back" })).toBeInTheDocument();
    });

    it("calls onDismiss when dismiss button is clicked", async () => {
      render(
        <WelcomeBackCard
          enrollment={enrollment}
          firstName="Lakshitha"
          onDismiss={onDismiss}
        />
      );
      await userEvent.click(screen.getByRole("button", { name: "Dismiss welcome back" }));
      expect(onDismiss).toHaveBeenCalledTimes(1);
    });
  });

  describe("resume button", () => {
    beforeEach(() => {
      mockUseResumeTarget.mockReturnValue({ isLoading: false, data: resumeTarget } as ReturnType<typeof useResumeTarget>);
    });

    it("shows 'Resume reading' when course is not complete", () => {
      render(
        <WelcomeBackCard
          enrollment={enrollment}
          firstName="Lakshitha"
          onDismiss={onDismiss}
        />
      );
      expect(screen.getByText("Resume reading")).toBeInTheDocument();
    });

    it("shows 'Review course' when course is complete", () => {
      const completeTarget: ResumeTarget = { ...resumeTarget, isCourseComplete: true };
      mockUseResumeTarget.mockReturnValue({ isLoading: false, data: completeTarget } as ReturnType<typeof useResumeTarget>);
      render(
        <WelcomeBackCard
          enrollment={enrollment}
          firstName="Lakshitha"
          onDismiss={onDismiss}
        />
      );
      expect(screen.getByText("Review course")).toBeInTheDocument();
    });

    it("resume link points to the URL from buildResumeUrl", () => {
      render(
        <WelcomeBackCard
          enrollment={enrollment}
          firstName="Lakshitha"
          onDismiss={onDismiss}
        />
      );
      const link = screen.getByRole("link", { name: /Resume reading/ });
      expect(link).toHaveAttribute("href", "/courses/c1/modules/m1/lessons/l1#section-s1");
    });

    it("calls buildResumeUrl with the resume target", () => {
      render(
        <WelcomeBackCard
          enrollment={enrollment}
          firstName="Lakshitha"
          onDismiss={onDismiss}
        />
      );
      expect(mockBuildResumeUrl).toHaveBeenCalledWith(resumeTarget);
    });
  });

  describe("section landmark", () => {
    beforeEach(() => {
      mockUseResumeTarget.mockReturnValue({ isLoading: false, data: resumeTarget } as ReturnType<typeof useResumeTarget>);
    });

    it("renders as a section element with aria-labelledby", () => {
      render(
        <WelcomeBackCard
          enrollment={enrollment}
          firstName="Lakshitha"
          onDismiss={onDismiss}
        />
      );
      const section = screen.getByRole("region", { name: "Welcome back, Lakshitha!" });
      expect(section).toBeInTheDocument();
    });
  });
});
