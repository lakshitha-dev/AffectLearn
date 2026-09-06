"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

import { apiFetch } from "@/lib/api-client";
import { useSessionStore } from "@/stores/session-store";

/**
 * The learner-facing half of the data rights the consent form and the privacy policy promise.
 *
 * Both documents commit to letting a participant see what is held about them and have it
 * deleted. Until these controls existed, exercising either meant emailing a researcher and
 * waiting — which is a favour, not a right, and it put the burden of the promise on somebody
 * remembering to keep it.
 *
 * Three deliberate choices here:
 *
 * - EXPORT IS OFFERED BEFORE DELETE, and the delete panel points at it. Someone about to erase
 *   their record should be one click from keeping a copy of it.
 * - DELETION ASKS FOR THE PASSWORD AND THE WORD "DELETE". A single confirm button is too easy to
 *   hit, and this is irreversible.
 * - THE RECEIPT IS SHOWN. The API returns per-table counts, and showing them is the difference
 *   between "we deleted your data" and evidence that it happened.
 */

type Receipt = Record<string, number>;

export function AccountDataControls() {
  const router = useRouter();
  const clearSession = useSessionStore((s) => s.clearSession);

  const [exporting, setExporting] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmWord, setConfirmWord] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setExporting(true);
    setError(null);
    try {
      const data = await apiFetch<unknown>("/auth/me/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `affectlearn-my-data-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Could not prepare your download. Please try again.");
    } finally {
      setExporting(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      const result = await apiFetch<{ deleted: Receipt }>("/auth/me/delete", {
        method: "POST",
        body: JSON.stringify({ password, confirm: confirmWord }),
      });
      setReceipt(result.deleted);
    } catch {
      setError(
        "That did not work. Check your password, and that you typed DELETE exactly.",
      );
      setDeleting(false);
    }
  }

  function finish() {
    clearSession();
    router.push("/");
  }

  // Deleted. The account no longer exists, so there is nothing to go back to — the only path
  // from here is out, and the receipt is the last chance to see what was removed.
  if (receipt) {
    const rows = Object.entries(receipt).filter(([, n]) => n > 0);
    return (
      <div className="rounded-lg border border-border bg-surface p-6">
        <h2 className="mb-1 font-semibold text-foreground">Your data has been deleted</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Your account and everything recorded about you has been removed. Here is exactly what
          went, so you have a record of it.
        </p>
        {rows.length > 0 ? (
          <ul className="mb-5 space-y-1 text-sm text-foreground">
            {rows.map(([table, n]) => (
              <li key={table} className="flex justify-between border-b border-border py-1.5">
                <span className="text-muted-foreground">{humanise(table)}</span>
                <span className="font-medium tabular-nums">{n}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mb-5 text-sm text-muted-foreground">
            There were no learning records to remove — only the account itself.
          </p>
        )}
        <button
          type="button"
          onClick={finish}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white"
        >
          Close
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-6">
      <h2 className="mb-1 font-semibold text-foreground">Your data</h2>
      <p className="mb-5 text-sm text-muted-foreground">
        You can take a copy of everything we hold about you, or remove it entirely. Neither
        requires asking us.
      </p>

      <div className="flex items-start justify-between gap-6 border-b border-border py-4">
        <div>
          <p className="text-sm font-medium text-foreground">Download my data</p>
          <p className="text-xs text-muted-foreground">
            A complete JSON file: your account, your progress, every quiz attempt, the help you
            were offered, and the interaction records. Not a summary.
          </p>
        </div>
        <button
          type="button"
          onClick={handleExport}
          disabled={exporting}
          className="shrink-0 rounded-md border border-border px-3 py-2 text-sm font-medium text-foreground disabled:opacity-60"
        >
          {exporting ? (
            <span className="flex items-center gap-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Preparing…
            </span>
          ) : (
            "Download"
          )}
        </button>
      </div>

      <div className="pt-4">
        <p className="text-sm font-medium text-foreground">Delete my account</p>
        <p className="mb-3 text-xs text-muted-foreground">
          Removes your account, your learning records and your research data. This cannot be
          undone — download a copy first if you want one.
        </p>

        {!confirmingDelete ? (
          <button
            type="button"
            onClick={() => setConfirmingDelete(true)}
            className="rounded-md border border-red-300 px-3 py-2 text-sm font-medium text-red-700 dark:border-red-800/50 dark:text-red-400"
          >
            Delete my account
          </button>
        ) : (
          <div className="space-y-3 rounded-md border border-red-200 bg-red-50 p-4 dark:border-red-800/40 dark:bg-red-900/10">
            <label className="block text-xs font-medium text-foreground">
              Your password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                className="mt-1 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              />
            </label>
            <label className="block text-xs font-medium text-foreground">
              Type <span className="font-mono font-semibold">DELETE</span> to confirm
              <input
                type="text"
                value={confirmWord}
                onChange={(e) => setConfirmWord(e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              />
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting || !password || confirmWord !== "DELETE"}
                className="rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {deleting ? "Deleting…" : "Delete everything"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setConfirmingDelete(false);
                  setPassword("");
                  setConfirmWord("");
                  setError(null);
                }}
                className="rounded-md border border-border px-3 py-2 text-sm font-medium text-foreground"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {error && (
        <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700 dark:border-red-800/40 dark:bg-red-900/10 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}

/** `quizAttempts` -> `Quiz attempts`. The receipt is for a person, not a schema reader. */
function humanise(key: string): string {
  const spaced = key.replace(/([A-Z])/g, " $1").toLowerCase().trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
