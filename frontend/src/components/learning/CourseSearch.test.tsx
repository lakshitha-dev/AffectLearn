import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CourseSearch } from "./CourseSearch";

describe("CourseSearch", () => {
  it("renders an accessible search input", () => {
    render(<CourseSearch value="" onChange={() => {}} />);
    expect(screen.getByRole("searchbox", { name: /Search courses/i })).toBeInTheDocument();
  });

  it("emits onChange for every keystroke (debouncing handled by caller)", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<CourseSearch value="" onChange={onChange} />);
    const input = screen.getByRole("searchbox");

    await user.type(input, "py");
    expect(onChange).toHaveBeenCalledTimes(2);
    expect(onChange).toHaveBeenLastCalledWith("y");
  });

  it("shows a clear button only when text is present", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <CourseSearch value="" onChange={onChange} />,
    );
    expect(screen.queryByRole("button", { name: /Clear search/i })).toBeNull();

    rerender(<CourseSearch value="python" onChange={onChange} />);
    const clearButton = screen.getByRole("button", { name: /Clear search/i });
    await user.click(clearButton);
    expect(onChange).toHaveBeenCalledWith("");
  });
});
