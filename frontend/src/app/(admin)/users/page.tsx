"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiFetch, ApiRequestError } from "@/lib/api-client";
import { useSessionStore } from "@/stores/session-store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type UserRole = "learner" | "course_designer" | "admin";

interface AdminUser {
  id: string;
  emailAddress: string;
  firstName: string;
  lastName: string;
  role: UserRole;
  isActive: boolean;
  emailVerified: boolean;
  createdAt: string | null;
  lastLoginAt: string | null;
}

interface PaginatedUsers {
  items: AdminUser[];
  total: number;
  page: number;
  pageSize: number;
}

interface UserStats {
  total: number;
  learners: number;
  courseDesigners: number;
  admins: number;
  verified: number;
  active: number;
}

const PAGE_SIZE = 20;

const ROLE_BADGE: Record<string, string> = {
  learner: "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  course_designer: "bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  admin: "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
};

const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: "learner", label: "Learner" },
  { value: "course_designer", label: "Course designer" },
  { value: "admin", label: "Admin" },
];

const roleLabel = (role: UserRole) =>
  ROLE_OPTIONS.find((r) => r.value === role)?.label ?? role.replace("_", " ");

// --- Create a user with a password + role (Story 8.1) ---

const createUserSchema = z.object({
  emailAddress: z.string().email("Please enter a valid email address"),
  firstName: z.string().min(1, "First name is required").max(100),
  lastName: z.string().min(1, "Last name is required").max(100),
  password: z
    .string()
    .min(8, "At least 8 characters")
    .regex(/[a-z]/, "Needs a lowercase letter")
    .regex(/[A-Z]/, "Needs an uppercase letter")
    .regex(/\d/, "Needs a digit")
    .regex(/[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?]/, "Needs a special character"),
  role: z.enum(["learner", "course_designer", "admin"]),
});
type CreateUserData = z.infer<typeof createUserSchema>;

function AddUserModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [serverError, setServerError] = useState<string | null>(null);
  const form = useForm<CreateUserData>({
    resolver: zodResolver(createUserSchema),
    mode: "onBlur",
    defaultValues: { role: "learner" },
  });
  const role = form.watch("role");

  const onSubmit = async (data: CreateUserData) => {
    setServerError(null);
    try {
      await apiFetch("/admin/users/create", { method: "POST", body: JSON.stringify(data) });
      toast.success("User created.");
      onCreated();
      onClose();
    } catch (err) {
      if (err instanceof ApiRequestError && err.errorCode === "DUPLICATE_EMAIL") {
        setServerError("A user with that email already exists.");
      } else {
        setServerError("Couldn't create the user. Please try again.");
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
        <h2 className="text-lg font-semibold text-foreground">Add a user</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Creates an active, verified account that can sign in immediately.
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

          <div className="space-y-2">
            <Label htmlFor="password">Password <span className="text-muted-foreground">*</span></Label>
            <PasswordInput
              id="password"
              autoComplete="new-password"
              className={`h-10 ${form.formState.errors.password ? "border-error" : ""}`}
              {...form.register("password")}
            />
            {form.formState.errors.password && (
              <p className="text-sm text-error">{form.formState.errors.password.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="role">Role <span className="text-muted-foreground">*</span></Label>
            <Select value={role} onValueChange={(v) => form.setValue("role", v as UserRole)}>
              <SelectTrigger id="role" className="h-10">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLE_OPTIONS.map((r) => (
                  <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? "Creating..." : "Create user"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// --- Invite a course designer (existing email set-password flow, AC3) ---

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
            <Label htmlFor="inviteEmail">Email <span className="text-muted-foreground">*</span></Label>
            <Input
              id="inviteEmail"
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
              <Label htmlFor="inviteFirst">First name <span className="text-muted-foreground">*</span></Label>
              <Input
                id="inviteFirst"
                className={`h-10 ${form.formState.errors.firstName ? "border-error" : ""}`}
                {...form.register("firstName")}
              />
              {form.formState.errors.firstName && (
                <p className="text-sm text-error">{form.formState.errors.firstName.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="inviteLast">Last name <span className="text-muted-foreground">*</span></Label>
              <Input
                id="inviteLast"
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

// --- Inline per-row role editor (AC4) ---

function RoleSelect({
  user,
  onChanged,
  disabled,
}: {
  user: AdminUser;
  onChanged: () => void;
  disabled?: boolean;
}) {
  const [saving, setSaving] = useState(false);

  const onChange = async (next: string) => {
    if (next === user.role) return;
    setSaving(true);
    try {
      await apiFetch(`/admin/users/${user.id}/role`, {
        method: "PATCH",
        body: JSON.stringify({ role: next }),
      });
      toast.success(`Role updated to ${roleLabel(next as UserRole)}.`);
      onChanged();
    } catch {
      toast.error("Couldn't update the role. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Select value={user.role} onValueChange={onChange} disabled={saving || disabled}>
      <SelectTrigger
        className="h-8 w-[150px]"
        aria-label={`Change role for ${user.firstName} ${user.lastName}`}
      >
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${ROLE_BADGE[user.role]}`}
        >
          {roleLabel(user.role)}
        </span>
      </SelectTrigger>
      <SelectContent>
        {ROLE_OPTIONS.map((r) => (
          <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

// --- Activate / deactivate confirm (AC5) ---

function StatusConfirm({
  user,
  onClose,
  onChanged,
}: {
  user: AdminUser;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const deactivating = user.isActive;

  const confirm = async () => {
    setBusy(true);
    try {
      await apiFetch(`/admin/users/${user.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ isActive: !user.isActive }),
      });
      toast.success(deactivating ? "User deactivated." : "User reactivated.");
      onChanged();
      onClose();
    } catch {
      toast.error("Couldn't update the account. Please try again.");
    } finally {
      setBusy(false);
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
        className="w-full max-w-sm rounded-lg border border-border bg-background p-6 shadow-lg"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-foreground">
          {deactivating ? "Deactivate user?" : "Reactivate user?"}
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          {deactivating
            ? `${user.firstName} ${user.lastName} will no longer be able to sign in until reactivated.`
            : `${user.firstName} ${user.lastName} will be able to sign in again.`}
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            type="button"
            variant={deactivating ? "destructive" : "default"}
            onClick={confirm}
            disabled={busy}
          >
            {busy ? "Saving..." : deactivating ? "Deactivate" : "Reactivate"}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function UsersPage() {
  const [addUserOpen, setAddUserOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [statusTarget, setStatusTarget] = useState<AdminUser | null>(null);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();
  const currentUserId = useSessionStore((s) => s.user?.id);

  // Debounce the search box so we issue one request after typing settles.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  // A new search resets to the first page so results aren't hidden on a stale page.
  useEffect(() => {
    setPage(1);
  }, [debouncedSearch]);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin", "users", "list", debouncedSearch, page],
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
      if (debouncedSearch) params.set("search", debouncedSearch);
      return apiFetch<PaginatedUsers>(`/admin/users?${params.toString()}`);
    },
  });

  // Summary counts across ALL users, independent of pagination/search.
  const stats = useQuery({
    queryKey: ["admin", "users", "stats"],
    queryFn: () => apiFetch<UserStats>("/admin/users/stats"),
  });

  const users = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const fmtDate = (iso: string | null) => (iso ? iso.slice(0, 10) : "—");
  // Prefix invalidation refreshes both the list (["admin","users","list",…]) and the
  // stats (["admin","users","stats"]) queries after any mutation.
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] });

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
            {stats.data?.total ?? 0} users
          </span>
          <Button variant="outline" onClick={() => setInviteOpen(true)}>Add designer</Button>
          <Button onClick={() => setAddUserOpen(true)}>Add user</Button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-8">
        {[
          { label: "Learners", value: stats.data?.learners ?? 0, color: "text-blue-600" },
          { label: "Course Designers", value: stats.data?.courseDesigners ?? 0, color: "text-purple-600" },
          { label: "Verified", value: stats.data?.verified ?? 0, color: "text-green-600" },
        ].map((stat) => (
          <div key={stat.label} className="rounded-lg border border-border bg-surface p-4">
            <p className="text-sm text-muted-foreground">{stat.label}</p>
            <p className={`mt-1 text-2xl font-bold ${stat.color}`}>{stat.value}</p>
          </div>
        ))}
      </div>

      <div className="mb-4">
        <Input
          type="search"
          placeholder="Search by name or email…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-10 max-w-sm"
          aria-label="Search users"
        />
      </div>

      <div className="rounded-lg border border-border bg-surface overflow-x-auto">
        {isLoading ? (
          <p className="p-6 text-sm text-muted-foreground">Loading users…</p>
        ) : isError ? (
          <p className="p-6 text-sm text-error">Couldn&apos;t load users. Please refresh.</p>
        ) : users.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">
            {debouncedSearch ? "No users match your search." : "No users yet."}
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-background">
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Name</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Email</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Role</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Last login</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Joined</th>
                <th className="px-4 py-3 text-right font-medium text-muted-foreground">Actions</th>
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
                    <RoleSelect
                      user={user}
                      onChanged={invalidate}
                      disabled={user.id === currentUserId}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${user.isActive ? "text-green-600" : "text-muted-foreground"}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${user.isActive ? "bg-green-500" : "bg-muted-foreground"}`} />
                      {user.isActive ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{fmtDate(user.lastLoginAt)}</td>
                  <td className="px-4 py-3 text-muted-foreground">{fmtDate(user.createdAt)}</td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={user.id === currentUserId}
                      title={user.id === currentUserId ? "You can't change your own status" : undefined}
                      onClick={() => setStatusTarget(user)}
                    >
                      {user.isActive ? "Deactivate" : "Reactivate"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {!isLoading && !isError && total > 0 && (
        <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Page {page} of {totalPages} · {total} {debouncedSearch ? "matching" : "total"}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      {addUserOpen && (
        <AddUserModal onClose={() => setAddUserOpen(false)} onCreated={invalidate} />
      )}
      {inviteOpen && (
        <AddDesignerModal onClose={() => setInviteOpen(false)} onCreated={invalidate} />
      )}
      {statusTarget && (
        <StatusConfirm
          user={statusTarget}
          onClose={() => setStatusTarget(null)}
          onChanged={invalidate}
        />
      )}
    </div>
  );
}
