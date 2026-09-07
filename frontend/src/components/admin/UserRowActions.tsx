"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  useUpdateUser,
  useWithdrawParticipant,
  type AdminUser,
  type UserRole,
} from "@/hooks/use-admin-users";
import { ApiRequestError } from "@/lib/api-client";

const ROLES: { value: UserRole; label: string }[] = [
  { value: "learner", label: "Learner" },
  { value: "course_designer", label: "Course designer" },
  { value: "admin", label: "Admin" },
];

/**
 * Role, activation and withdrawal controls for one account (Stories 8.1 and 8.7).
 *
 * The console could previously list and invite and nothing else — there was no way to promote a
 * designer, deactivate a leaver, or action a withdrawal request, all of which Epic 8 asks for.
 *
 * `currentUserId` is passed so the row for the signed-in admin renders WITHOUT these controls.
 * The server refuses self-demotion and self-deactivation anyway — it is the only role that can
 * grant the role back, and a sole admin who clicks the wrong row locks the deployment out of its
 * own administration — but a disabled-looking button that errors is a worse way to say so than
 * not offering it.
 */
export function UserRowActions({
  user,
  currentUserId,
}: {
  user: AdminUser;
  currentUserId: string | undefined;
}) {
  const updateUser = useUpdateUser();
  const withdraw = useWithdrawParticipant();
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);
  const [receipt, setReceipt] = useState<Record<string, number> | null>(null);

  const isSelf = user.id === currentUserId;

  async function changeRole(role: UserRole) {
    if (role === user.role) return;
    try {
      await updateUser.mutateAsync({ userId: user.id, role });
      toast.success(`${user.firstName} is now a ${role.replace("_", " ")}`);
    } catch (err) {
      toast.error(
        err instanceof ApiRequestError && err.errorCode === "CANNOT_SELF_ADMINISTER"
          ? "You cannot change your own role"
          : "Could not change the role"
      );
    }
  }

  async function toggleActive() {
    try {
      await updateUser.mutateAsync({ userId: user.id, isActive: !user.isActive });
      toast.success(user.isActive ? "Account deactivated" : "Account reactivated");
    } catch {
      toast.error("Could not change the account status");
    }
  }

  async function confirm() {
    try {
      const result = await withdraw.mutateAsync({ userId: user.id });
      setReceipt(result.deleted);
    } catch (err) {
      toast.error(
        err instanceof ApiRequestError && err.errorCode === "CANNOT_WITHDRAW_ADMIN"
          ? "Administrator accounts are not study participants"
          : "Could not withdraw this participant"
      );
    }
  }

  if (isSelf) {
    return <span className="text-xs text-muted-foreground">Your account</span>;
  }

  return (
    <div className="flex items-center justify-end gap-2">
      <select
        aria-label={`Role for ${user.firstName} ${user.lastName}`}
        value={user.role}
        disabled={updateUser.isPending}
        onChange={(e) => changeRole(e.target.value as UserRole)}
        className="h-8 rounded-md border border-border bg-background px-2 text-xs focus:outline-none focus:ring-2 focus:ring-primary"
      >
        {ROLES.map((role) => (
          <option key={role.value} value={role.value}>
            {role.label}
          </option>
        ))}
      </select>

      <button
        type="button"
        onClick={toggleActive}
        disabled={updateUser.isPending}
        className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline disabled:opacity-50"
      >
        {user.isActive ? "Deactivate" : "Reactivate"}
      </button>

      {user.role !== "admin" && (
        <button
          type="button"
          onClick={() => setConfirmWithdraw(true)}
          className="text-xs text-muted-foreground underline-offset-4 hover:text-destructive hover:underline"
        >
          Withdraw
        </button>
      )}

      <Dialog
        open={confirmWithdraw}
        onOpenChange={(open) => {
          setConfirmWithdraw(open);
          if (!open) setReceipt(null);
        }}
      >
        <DialogContent className="max-w-md">
          {receipt ? (
            <>
              <DialogHeader>
                <DialogTitle>Participant withdrawn</DialogTitle>
                <DialogDescription>
                  Everything recorded about {user.firstName} {user.lastName} has been deleted.
                  Keep this receipt — it is the record that the erasure happened.
                </DialogDescription>
              </DialogHeader>
              <ul className="mt-3 space-y-1 text-sm">
                {Object.entries(receipt).map(([table, count]) => (
                  <li key={table} className="flex justify-between">
                    <span className="text-muted-foreground">{table}</span>
                    <span className="font-mono text-foreground">{count}</span>
                  </li>
                ))}
              </ul>
              <DialogFooter>
                <Button
                  onClick={() => {
                    setConfirmWithdraw(false);
                    setReceipt(null);
                  }}
                >
                  Done
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle>
                  Withdraw {user.firstName} {user.lastName}?
                </DialogTitle>
                {/* The spec'd wording. It is blunt because the action is. */}
                <DialogDescription>
                  This will permanently delete all data for this participant. This cannot be
                  undone.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setConfirmWithdraw(false)}>
                  Cancel
                </Button>
                <Button onClick={confirm} disabled={withdraw.isPending}>
                  {withdraw.isPending ? "Withdrawing…" : "Withdraw and delete"}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
