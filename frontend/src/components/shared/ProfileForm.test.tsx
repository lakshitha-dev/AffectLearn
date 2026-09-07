/**
 * Tests for the shared profile form.
 *
 * The designer settings page it replaces displayed a hardcoded "Dr. Morgan / morgan@university.edu
 * / Computer Science" behind disabled inputs. The two things worth pinning here are that the form
 * shows the SIGNED-IN user rather than any fixed value, and that email and role cannot be edited
 * through it.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createElement } from "react";

const mutateAsync = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-profile", () => ({
  useUpdateProfile: () => ({ mutateAsync, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const user = {
  id: "u1",
  emailAddress: "real.designer@example.edu",
  firstName: "Real",
  lastName: "Designer",
  role: "course_designer" as const,
  ageRange: "25-34",
  degreeProgram: "Computer Science",
};

vi.mock("@/stores/session-store", () => ({
  useSessionStore: (selector: (s: { user: typeof user }) => unknown) => selector({ user }),
}));

import { ProfileForm } from "./ProfileForm";

beforeEach(() => {
  mutateAsync.mockReset();
  mutateAsync.mockResolvedValue(user);
});

describe("ProfileForm", () => {
  it("shows the signed-in account, not placeholder details", () => {
    render(createElement(ProfileForm));

    expect(screen.getByLabelText("First name")).toHaveValue("Real");
    expect(screen.getByLabelText("Last name")).toHaveValue("Designer");
    expect(screen.getByText("real.designer@example.edu")).toBeInTheDocument();
  });

  it("does not offer email or role as editable fields", () => {
    render(createElement(ProfileForm));

    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/role/i)).not.toBeInTheDocument();
  });

  it("saves only after a change, and sends the edited values", async () => {
    const u = userEvent.setup();
    render(createElement(ProfileForm));

    // Nothing edited yet — the button stays disabled rather than firing a no-op write.
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();

    const first = screen.getByLabelText("First name");
    await u.clear(first);
    await u.type(first, "Morgan");
    await u.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        firstName: "Morgan",
        lastName: "Designer",
        ageRange: "25-34",
        degreeProgram: "Computer Science",
      })
    );
  });

  it("sends null rather than an empty string when a field is cleared", async () => {
    const u = userEvent.setup();
    render(createElement(ProfileForm));

    await u.clear(screen.getByLabelText("Degree programme"));
    await u.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({ degreeProgram: null })
      )
    );
  });

  it("rejects a blank name", async () => {
    const u = userEvent.setup();
    render(createElement(ProfileForm));

    await u.clear(screen.getByLabelText("First name"));
    await u.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("First name is required")).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });
});
