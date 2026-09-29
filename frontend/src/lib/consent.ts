/**
 * What the learner has consented to, as the browser needs it (mirrors `backend/app/services/consent.py`).
 *
 * The server enforces consent on every capture message; this is the browser's half, so that
 * capture which would be refused is never started in the first place (no camera light, no
 * listeners) rather than started and silently dropped.
 */
import type { ConsentScopes, UserResponse } from "@/types/api-responses";

/** The consent text shown by `ConsentStep`. Bump it with the text; the server records it. */
export const CONSENT_VERSION = "2026-09-pilot-v1";

export const DEFAULT_SCOPES: ConsentScopes = { behavioural: true, rawInteraction: false };

export interface CaptureConsent {
  /** Consented and not withdrawn: any research capture at all. */
  participating: boolean;
  /** Mouse / keyboard-category / scroll windows and the performance window. */
  behavioural: boolean;
}

export function captureConsent(user: UserResponse | null | undefined): CaptureConsent {
  const participating = Boolean(user?.consentGivenAt) && !user?.consentWithdrawnAt;
  const scopes = user?.consentScopes ?? DEFAULT_SCOPES;
  return { participating, behavioural: participating && scopes.behavioural !== false };
}
