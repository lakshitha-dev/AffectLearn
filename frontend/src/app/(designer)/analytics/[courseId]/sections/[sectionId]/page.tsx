"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { AffectDistributionBars } from "@/components/designer/AffectDistributionBars";
import { ContentHotspotPreview } from "@/components/designer/ContentHotspotPreview";
import { QuestionAnalysis } from "@/components/designer/QuestionAnalysis";
import { SectionDetailSkeleton } from "@/components/designer/SectionDetailSkeleton";
import { useSectionDetail } from "@/hooks/use-analytics";
import type { SectionInsights } from "@/types/analytics";

/**
 * Section-detail route — the Story 7.3 → 7.4 click-through target (FINAL story of
 * Epic 7). Replaces the 7.3 placeholder body with the real three-panel section
 * detail: (1) Affect Distribution bars, (2) Key Insights, (3) Content Preview
 * with hotspot highlighting.
 *
 * ROUTING: the URL is `(designer)/analytics/[courseId]/sections/[sectionId]`,
 * nested under the course so the heatmap → section-detail → back-to-heatmap
 * breadcrumb is natural. Keeps the placeholder's `"use client"`, `useParams`
 * reads, header, and "← Back to heatmap" link.
 *
 * DATA: `useSectionDetail(sectionId)` → `GET /analytics/sections/{sectionId}/detail`
 * (the verified 7.1 contract — do NOT invent fields).
 *
 * EDIT CONTENT (AC8): "Edit Content" navigates to the editor INDEX `/content-editor`,
 * NOT the deep `/editor/[courseId]/[moduleId]/[lessonId]` route, because the
 * `SectionDetailResponse` is section-keyed only and returns NO `moduleId`/`lessonId`
 * for the section's parent lesson. Deep-linking the exact lesson editor with the
 * section preloaded would require the detail endpoint to also return those IDs —
 * flagged as an Open Question / future 7.1 enhancement. (Backend change → out of
 * this frontend story's scope.)
 *
 * KEY INSIGHTS (AC3): the panel shows ONLY the two fields the backend returns —
 * `mostTriggeredAdaptationType` + `averageConfusionDurationSeconds`. The original
 * epic AC listed two more ("% needed hints", "% took breaks"); those were REMOVED
 * from the backend `SectionInsights` schema in the 7.1 review and are NOT returned.
 * This page's AC3 supersedes the epic text — do NOT add or fabricate them.
 */

/** Format a duration in seconds as "12s" or "1m 03s". */
function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  const rem = total % 60;
  return `${minutes}m ${String(rem).padStart(2, "0")}s`;
}

function KeyInsightsPanel({ insights }: { insights: SectionInsights }) {
  const adaptation = insights.mostTriggeredAdaptationType;
  const duration = insights.averageConfusionDurationSeconds;

  return (
    <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
      <h2 className="text-sm font-semibold text-foreground">Key Insights</h2>
      <dl className="mt-4 space-y-4">
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Most-Triggered Adaptation
          </dt>
          <dd className="mt-1 text-lg font-semibold text-foreground">
            {adaptation ?? "None"}
          </dd>
          {adaptation ? null : (
            <p className="text-xs text-muted-foreground">
              No adaptations triggered
            </p>
          )}
        </div>
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Average Confusion Duration
          </dt>
          <dd className="mt-1 text-lg font-semibold text-foreground">
            {duration == null ? "—" : formatDuration(duration)}
          </dd>
        </div>
      </dl>
    </div>
  );
}

export default function SectionDetailPage() {
  const params = useParams<{ courseId: string; sectionId: string }>();
  const courseId = params?.courseId ?? "";
  const sectionId = params?.sectionId ?? "";

  const detailQuery = useSectionDetail(sectionId);
  const data = detailQuery.data;
  const limited = data
    ? data.insufficientData || data.confidence === "low"
    : false;

  return (
    <div>
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link
            href={`/analytics/${courseId}`}
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            ← Back to heatmap
          </Link>
          <div className="mt-2 flex items-center gap-3">
            <h1 className="text-2xl font-bold text-foreground">
              {data?.sectionTitle ?? "Section Detail"}
            </h1>
            {limited ? (
              <span className="inline-flex items-center rounded-full bg-muted/15 px-2 py-0.5 text-xs font-medium text-muted-foreground">
                Limited data
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Affect breakdown, key insights, and content hotspots for this section
          </p>
        </div>

        {/* Edit Content → editor index (see AC8 note above). */}
        <Link
          href="/content-editor"
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          Edit Content
        </Link>
      </div>

      {detailQuery.isPending ? (
        <SectionDetailSkeleton />
      ) : detailQuery.isError ? (
        <div className="rounded-lg border border-border bg-surface px-5 py-12 text-center">
          <p className="text-sm font-medium text-foreground">
            Couldn&apos;t load the section detail
          </p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            {(detailQuery.error as Error)?.message ?? "Something went wrong."}
          </p>
          <button
            type="button"
            onClick={() => detailQuery.refetch()}
            className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Retry
          </button>
        </div>
      ) : data ? (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Panel 1: Affect Distribution */}
            <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-foreground">
                Affect Distribution
              </h2>
              <p className="mb-5 mt-1 text-xs text-muted-foreground">
                Per-learner share for this section — values may sum to more than
                100%.
              </p>
              <AffectDistributionBars distribution={data.affectDistribution} />
            </div>

            {/* Panel 2: Key Insights */}
            <KeyInsightsPanel insights={data.keyInsights} />
          </div>

          {/* Panel 3: Content Preview with hotspots */}
          <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
            <h2 className="mb-5 text-sm font-semibold text-foreground">
              Content Preview
            </h2>
            <ContentHotspotPreview
              content={data.content}
              temporalDistribution={data.temporalDistribution}
              insufficientData={data.insufficientData}
            />
          </div>

          {/*
            Panel 4: per-question item analysis. The endpoint and its typed hook already existed
            and nothing rendered them, so a designer could see that a SECTION caused confusion
            without seeing which question inside it did.
          */}
          <QuestionAnalysis sectionId={sectionId} />
        </div>
      ) : null}
    </div>
  );
}
