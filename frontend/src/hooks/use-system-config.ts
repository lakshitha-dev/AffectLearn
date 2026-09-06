"use client";

/**
 * Query hook for the runtime system-configuration endpoints.
 *
 * These back the admin settings page, which until now rendered seven hardcoded `<input disabled>`
 * values — decorative numbers that already disagreed with the live gate, since `/monitor/health`
 * reports the real thresholds. Reading the real endpoint is the point.
 */

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";

export const SYSTEM_CONFIG_KEY = "system-config";

export type ForcedMode = "auto" | "facial_only" | "behavioral_only" | "multimodal";

export interface ConfigValues {
  withholdRate: number;
  maxPerSession: number;
  minConfidence: number;
  minConfidenceGeometry: number;
  minConfidenceBehavioral: number;
  minConsecutive: number;
  cooldownCycles: number;
  adaptStates: string[];
  decisiveSources: string[];
  fusionDrivesDecision: boolean;
  forcedMode: ForcedMode | string;
}

export interface LlmKeyStatus {
  configured: boolean;
  /** Last four characters only. The key itself is never returned by any endpoint. */
  hint: string | null;
  updatedAt: string | null;
  /** False when no encryption secret is available, so the UI can explain rather than fail. */
  canRotate: boolean;
}

export interface SystemConfig {
  /** Increments on every change and is stamped onto every research event. */
  version: number;
  locked: boolean;
  values: ConfigValues;
  /** Keys explicitly overridden, as opposed to inherited from the environment default. */
  overridden: string[];
  llmKey: LlmKeyStatus;
}

export function useSystemConfig() {
  return useQuery<SystemConfig>({
    queryKey: [SYSTEM_CONFIG_KEY],
    queryFn: () => apiFetch<SystemConfig>("/admin/config"),
    staleTime: 10_000,
  });
}

/** Apply overrides. A value of `null` clears an override and restores the default. */
export async function patchSystemConfig(
  changes: Partial<Record<keyof ConfigValues, unknown>>,
): Promise<SystemConfig> {
  return apiFetch<SystemConfig>("/admin/config", {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export async function setConfigLock(locked: boolean): Promise<SystemConfig> {
  return apiFetch<SystemConfig>("/admin/config/lock", {
    method: "POST",
    body: JSON.stringify({ locked }),
  });
}

/** Write-only: the key is sent, and nothing capable of carrying it comes back. */
export async function rotateLlmKey(apiKey: string): Promise<LlmKeyStatus> {
  return apiFetch<LlmKeyStatus>("/admin/config/llm-key", {
    method: "PUT",
    body: JSON.stringify({ apiKey }),
  });
}
