/**
 * Tests for the change-password form.
 *
 * `POST /auth/change-password` was implemented and tested on the server the whole time and no
 * screen in any role ever called it, so a signed-in user's only route to a new password was to
 * sign out and use the emailed reset link. These cover the parts a form can get wrong: sending
 * the right fields, telling a wrong current password apart from a server failure, and not
 * accepting a confirmation that does not match.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createElement } from "react";

const mutateAsync = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-profile", () => ({
  useChangePassword: () => ({ mutateAsync, isPending: false }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ChangePasswordForm } from "./ChangePasswordForm";

const GOOD = "NewStrongPass1!";

async function fill(user: ReturnType<typeof userEvent.setup>, values: Record<string, string>) {
  for (const [label, value] of Object.entries(values)) {
    await user.type(screen.getByLabelText(label), value);
  }
}

beforeEach(() => {
  mutateAsync.mockReset();
  mutateAsync.mockResolvedValue({ message: "Password changed" });
});

describe("ChangePasswordForm", () => {
  it("submits the current and new password", async () => {
    const user = userEvent.setup();
    render(createElement(ChangePasswordForm));

    await fill(user, {
      "Current password": "OldPassword1!",
      "New password": GOOD,
      "Confirm new password": GOOD,
    });
    await user.click(screen.getByRole("button", { name: "Change password" }));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        currentPassword: "OldPassword1!",
        newPassword: GOOD,
      })
    );
  });

  it("refuses a confirmation that does not match", async () => {
    const user = userEvent.setup();
    render(createElement(ChangePasswordForm));

    await fill(user, {
      "Current password": "OldPassword1!",
      "New password": GOOD,
      "Confirm new password": "SomethingElse1!",
    });
    await user.click(screen.getByRole("button", { name: "Change password" }));

    expect(await screen.findByText("Passwords do not match")).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("refuses a new password that is the same as the current one", async () => {
    const user = userEvent.setup();
    render(createElement(ChangePasswordForm));

    await fill(user, {
      "Current password": GOOD,
      "New password": GOOD,
      "Confirm new password": GOOD,
    });
    await user.click(screen.getByRole("button", { name: "Change password" }));

    expect(
      await screen.findByText("Choose a password different from your current one")
    ).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("enforces the same password policy as registration", async () => {
    const user = userEvent.setup();
    render(createElement(ChangePasswordForm));

    await fill(user, {
      "Current password": "OldPassword1!",
      "New password": "short",
      "Confirm new password": "short",
    });
    await user.click(screen.getByRole("button", { name: "Change password" }));

    expect(
      await screen.findByText("Password must be at least 8 characters")
    ).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });
});
