"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiFetch, ApiRequestError } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface AdminUser {
  id: string;
  emailAddress: string;
  firstName: string;
  lastName: string;
  role: "learner" | "course_designer" | "admin";
  isActive: boolean;
  emailVerified: boolean;
  createdAt: string | null;
}

interface PaginatedUsers {
  items: AdminUser[];
  total: number;
  page: number;
  pageSize: number;
}

const ROLE_BADGE: Record<string, string> = {
  learner: "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  course_designer: "bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  admin: "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
};

const inviteSchema = z.object({
  emailAddress: z.string().email("Please enter a valid email address"),
  firstName: z.string().min(1, "First name is required").max(100),
  lastName: z.string().min(1, "Last name is required").max(100),
});
type InviteData = z.infer<typeof inviteSchema>;

function AddDesignerModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [serverError, setServerError] = useState<string | null>(null);
  const form = useForm<InviteData>({ resolver: zodResolver(inviteSchema), mode: "onBlur" });

  const onSubmit = async (data: InviteData) => {
    setServerError(null);
    try {
      await apiFetch("/admin/users", { method: "POST", body: JSON.stringify(data) });
      toast.success("Designer invited — they'll get an email to set their password.");
      onCreated();
      onClose();
    } catch (err) {
      if (err instanceof ApiRequestError && err.errorCode === "DUPLICATE_EMAIL") {
        setServerError("A user with that email already exists.");
      } else {
        setServerError("Couldn't create the designer. Please try again.");
      }
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      onMouseDown={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-border bg-background p-6 shadow-lg"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-foreground">Add a course designer</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          They&apos;ll receive an email to set their own password. No password needed here.
        </p>

        <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="mt-5 space-y-4">
          {serverError && (
            <div className="rounded-md border border-error/30 bg-error/5 p-3 text-sm text-error" role="alert">
              {serverError}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="emailAddress">Email <span className="text-muted-foreground">*</span></Label>
            <Input
              id="emailAddress"
              type="email"
              autoComplete="off"
              className={`h-10 ${form.formState.errors.emailAddress ? "border-error" : ""}`}
              {...form.register("emailAddress")}
            />
            {form.formState.errors.emailAddress && (
              <p className="text-sm text-error">{form.formState.errors.emailAddress.message}</p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="firstName">First name <span className="text-muted-foreground">*</span></Label>
              <Input
                id="firstName"
                className={`h-10 ${form.formState.errors.firstName ? "border-error" : ""}`}
                {...form.register("firstName")}
              />
              {form.formState.errors.firstName && (
                <p className="text-sm text-error">{form.formState.errors.firstName.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="lastName">Last name <span className="text-muted-foreground">*</span></Label>
              <Input
                id="lastName"
                className={`h-10 ${form.formState.errors.lastName ? "border-error" : ""}`}
                {...form.register("lastName")}
              />
              {form.formState.errors.lastName && (
                <p className="text-sm text-error">{form.formState.errors.lastName.message}</p>
              )}
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? "Inviting..." : "Send invite"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function UsersPage() {
  const [modalOpen, setModalOpen] = useState(false);
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => apiFetch<PaginatedUsers>("/admin/users?page=1&page_size=100"),
  });

  const users = data?.items ?? [];
  const fmtDate = (iso: string | null) => (iso ? iso.slice(0, 10) : "—");

  return (
    <div>
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">User Management</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage learner, designer, and admin accounts
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="rounded-full bg-primary/10 px-3 py-1 text-sm font-medium text-primary">
            {data?.total ?? 0} users
          </span>
          <Button onClick={() => setModalOpen(true)}>Add designer</Button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-8">
        {[
          { label: "Learners", value: users.filter((u) => u.role === "learner").length, color: "text-blue-600" },
          { label: "Course Designers", value: users.filter((u) => u.role === "course_designer").length, color: "text-purple-600" },
          { label: "Verified", value: users.filter((u) => u.emailVerified).length, color: "text-green-600" },
        ].map((stat) => (
          <div key={stat.label} className="rounded-lg border border-border bg-surface p-4">
            <p className="text-sm text-muted-foreground">{stat.label}</p>
            <p className={`mt-1 text-2xl font-bold ${stat.color}`}>{stat.value}</p>
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        {isLoading ? (
          <p className="p-6 text-sm text-muted-foreground">Loading users…</p>
        ) : isError ? (
          <p className="p-6 text-sm text-error">Couldn&apos;t load users. Please refresh.</p>
        ) : users.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">No users yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-background">
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Name</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Email</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Role</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Joined</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user, i) => (
                <tr key={user.id} className={`border-b border-border last:border-0 ${i % 2 === 0 ? "" : "bg-background/50"}`}>
                  <td className="px-4 py-3 font-medium text-foreground">
                    {user.firstName} {user.lastName}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{user.emailAddress}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${ROLE_BADGE[user.role]}`}>
                      {user.role.replace("_", " ")}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${user.emailVerified ? "text-green-600" : "text-amber-600"}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${user.emailVerified ? "bg-green-500" : "bg-amber-500"}`} />
                      {user.emailVerified ? "Verified" : "Pending"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{fmtDate(user.createdAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {modalOpen && (
        <AddDesignerModal
          onClose={() => setModalOpen(false)}
          onCreated={() => queryClient.invalidateQueries({ queryKey: ["admin", "users"] })}
        />
      )}
    </div>
  );
}
