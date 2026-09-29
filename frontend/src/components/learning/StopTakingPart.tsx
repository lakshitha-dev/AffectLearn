"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useGiveConsent, useWithdrawConsent } from "@/hooks/use-onboarding";
import { DEFAULT_SCOPES } from "@/lib/consent";
import { useSessionStore } from "@/stores/session-store";

/**
 * The participant's right to stop at any time, separate from deleting their data.
 *
 * Deleting the account is irreversible, so offering only that would make "stop" an all-or-nothing
 * decision taken in the moment. This stops every kind of recording at once (the server refuses
 * capture within seconds, and the lesson page stops the camera and the listeners), keeps the
 * account, and leaves the data decision for later -- which is what the consent form promises.
 */
export function StopTakingPart() {
  const user = useSessionStore((s) => s.user);
  const withdraw = useWithdrawConsent();
  const rejoin = useGiveConsent();
  const [confirming, setConfirming] = useState(false);

  const withdrawn = Boolean(user?.consentWithdrawnAt);
  const busy = withdraw.isPending || rejoin.isPending;

  return (
    <div className="rounded-lg border border-border bg-surface p-6">
      <h2 className="mb-1 font-semibold text-foreground">Taking part in the study</h2>
      {withdrawn ? (
        <>
          <p className="mb-4 text-sm text-muted-foreground">
            You have stopped taking part. Nothing about your learning is being recorded for the
            study. You can still use the courses, delete your data below, or rejoin.
          </p>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => rejoin.mutate(user?.consentScopes ?? DEFAULT_SCOPES)}
          >
            {rejoin.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Rejoin the study
          </Button>
        </>
      ) : (
        <>
          <p className="mb-4 text-sm text-muted-foreground">
            You can stop at any time without giving a reason. All recording — camera measurements,
            mouse and keyboard activity, and the feeling check-ins — stops straight away. Your
            account and what was already recorded are kept until you decide; you can delete them
            below.
          </p>
          {confirming ? (
            <div className="flex flex-wrap gap-3">
              <Button
                variant="destructive"
                disabled={busy}
                onClick={() => withdraw.mutate(undefined, { onSettled: () => setConfirming(false) })}
              >
                {withdraw.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Yes, stop recording
              </Button>
              <Button variant="outline" disabled={busy} onClick={() => setConfirming(false)}>
                Cancel
              </Button>
            </div>
          ) : (
            <Button variant="outline" onClick={() => setConfirming(true)}>
              Stop taking part
            </Button>
          )}
        </>
      )}
      {(withdraw.isError || rejoin.isError) && (
        <p className="mt-3 text-xs text-red-600" role="alert">
          That did not save. Please try again, or tell the researcher.
        </p>
      )}
    </div>
  );
}
