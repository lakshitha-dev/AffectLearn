import { describe, expect, it } from "vitest";

import { captureConsent } from "./consent";
import type { UserResponse } from "@/types/api-responses";

const base: UserResponse = {
  id: "u", emailAddress: "p001@pilot.affectlearn.io", firstName: "P001", lastName: "-",
  role: "learner", consentGivenAt: "2026-10-01T09:00:00Z",
};

describe("captureConsent", () => {
  it("captures a consented learner with default scopes", () => {
    expect(captureConsent(base)).toEqual({ participating: true, behavioural: true });
  });

  it("captures nothing before consent", () => {
    expect(captureConsent({ ...base, consentGivenAt: null })).toEqual({
      participating: false, behavioural: false,
    });
  });

  it("captures nothing after withdrawal", () => {
    expect(captureConsent({ ...base, consentWithdrawnAt: "2026-10-01T09:30:00Z" })).toEqual({
      participating: false, behavioural: false,
    });
  });

  it("honours a declined behavioural scope", () => {
    const user = { ...base, consentScopes: { behavioural: false, rawInteraction: false } };
    expect(captureConsent(user)).toEqual({ participating: true, behavioural: false });
  });

  it("treats a missing user as not consented", () => {
    expect(captureConsent(null).participating).toBe(false);
  });
});
