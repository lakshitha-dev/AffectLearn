import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { CourseCard } from "./CourseCard";
import type { Course } from "@/types/course";

const baseCourse: Course = {
  id: "11111111-1111-1111-1111-111111111111",
  title: "Intro to Python",
  description: "A friendly first course",
  estimatedDurationMinutes: 90,
  isPublished: true,
  createdAt: "2026-04-01T00:00:00Z",
  updatedAt: "2026-04-01T00:00:00Z",
  moduleCount: 4,
};

describe("CourseCard", () => {
  it("renders title, description, duration and module count", () => {
    render(<CourseCard course={baseCourse} />);
    expect(screen.getByText("Intro to Python")).toBeInTheDocument();
    expect(screen.getByText("A friendly first course")).toBeInTheDocument();
    expect(screen.getByText(/1\.5 h/)).toBeInTheDocument();
    expect(screen.getByText(/4 modules/)).toBeInTheDocument();
  });

  it("renders an accessible link to the course overview", () => {
    render(<CourseCard course={baseCourse} />);
    const link = screen.getByRole("link", { name: /Open course/ });
    expect(link).toHaveAttribute("href", `/courses/${baseCourse.id}`);
  });

  it("renders progress bar and continue copy in enrolled variant", () => {
    render(
      <CourseCard course={baseCourse} variant="enrolled" progress={42} />,
    );
    const progress = screen.getByRole("progressbar");
    expect(progress).toHaveAttribute("aria-valuenow", "42");
    expect(progress).toHaveAttribute("aria-valuemin", "0");
    expect(progress).toHaveAttribute("aria-valuemax", "100");
    expect(screen.getByText(/Continue/)).toBeInTheDocument();
  });

  it("clamps progress to 0..100 and shows Start Learning at 0%", () => {
    render(<CourseCard course={baseCourse} variant="enrolled" progress={0} />);
    expect(screen.getByText(/Start Learning/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "0",
    );
  });

  it("shows minute units for short courses", () => {
    render(
      <CourseCard
        course={{ ...baseCourse, estimatedDurationMinutes: 45 }}
      />,
    );
    expect(screen.getByText(/45 min/)).toBeInTheDocument();
  });

  it("singularizes module label when count is 1", () => {
    render(<CourseCard course={{ ...baseCourse, moduleCount: 1 }} />);
    expect(screen.getByText(/1 module/)).toBeInTheDocument();
    expect(screen.queryByText(/1 modules/)).not.toBeInTheDocument();
  });
});
