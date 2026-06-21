import { cn } from "@/lib/cn";
import type { Confidence } from "@/types/analytics";

interface StatCardProps {
  label: string;
  /** Preformatted metric value (e.g. "72%", "1,204"). */
  value: string;
  /**
   * Honest supporting indicator. The 7.1 contract supplies `confidence` +
   * `sampleCount` rather than a period-over-period delta, so we surface those
   * instead of fabricating a fake "+12% vs last week" trend (see Dev Notes).
   */
  indicator?: string;
  confidence?: Confidence;
  insufficientData?: boolean;
}

const CONFIDENCE_DOT: Record<Confidence, string> = {
  high: "bg-success",
  medium: "bg-warning",
  low: "bg-muted",
};

/**
 * Azure-inspired analytics stat card: `--surface` panel, rounded border, shadow;
 * a large metric value, a label, and a supporting confidence/sample indicator.
 *
 * When the backend reports `insufficientData` (or low `confidence`) the card
 * renders a muted "Limited data" badge so thin data is never presented as
 * authoritative.
 */
export function StatCard({
  label,
  value,
  indicator,
  confidence,
  insufficientData,
}: StatCardProps) {
  const limited = insufficientData || confidence === "low";

  return (
    <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
        {limited ? (
          <span className="inline-flex items-center rounded-full bg-muted/15 px-2 py-0.5 text-xs font-medium text-muted-foreground">
            Limited data
          </span>
        ) : null}
      </div>
      <p
        className={cn(
          "mt-3 text-3xl font-bold tracking-tight",
          limited ? "text-muted-foreground" : "text-foreground"
        )}
      >
        {value}
      </p>
      {indicator ? (
        <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
          {confidence ? (
            <span
              aria-hidden="true"
              className={cn("h-2 w-2 rounded-full", CONFIDENCE_DOT[confidence])}
            />
          ) : null}
          <span>{indicator}</span>
        </div>
      ) : null}
    </div>
  );
}
