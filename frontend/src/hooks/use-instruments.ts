"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";
import type { InstrumentName } from "@/components/study/instruments";

export interface InstrumentRecord {
  id: string;
  instrument: InstrumentName;
  instrumentVersion: string;
  context?: Record<string, string> | null;
  skipped: boolean;
  submittedAt: string;
}

/** Store one administration of a pilot questionnaire (`POST /instruments/{name}`). */
export function useSubmitInstrument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      instrument: InstrumentName;
      version: string;
      responses: Record<string, string>;
      skipped: boolean;
      shownAt: string;
      context?: Record<string, string>;
    }) =>
      apiFetch<InstrumentRecord>(`/instruments/${args.instrument}`, {
        method: "POST",
        body: JSON.stringify({
          instrumentVersion: args.version,
          responses: args.responses,
          skipped: args.skipped,
          shownAt: args.shownAt,
          context: args.context,
        }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["instruments", "mine"] }),
  });
}

/** What this learner has already answered, so a lesson is not asked about twice. */
export function useMyInstruments(instrument: InstrumentName, enabled = true) {
  return useQuery({
    queryKey: ["instruments", "mine", instrument],
    queryFn: () =>
      apiFetch<InstrumentRecord[]>(`/instruments/mine?instrument=${instrument}`),
    enabled,
    staleTime: 60_000,
  });
}
