"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

/**
 * Section-detail route — the Story 7.3 → 7.4 click-through target.
 *
 * ROUTING DECISION (documented for Story 7.4): the agreed section-detail URL is
 * `(designer)/analytics/[courseId]/sections/[sectionId]` →
 * `/analytics/<courseId>/sections/<sectionId>`, nested under the course so the
 * heatmap → section-detail → back-to-heatmap breadcrumb is natural. Story 7.3
 * ships this PLACEHOLDER (resolves cleanly inside the designer layout, never a
 * 404) so heatmap-row clicks land somewhere real; Story 7.4 replaces this body
 * with the three-panel detail (affect bars, key insights, content hotspot
 * preview). Mirrors how Story 7.2 stubbed the `[courseId]` route for 7.3.
 */
export default function SectionDetailPlaceholderPage() {
  const params = useParams<{ courseId: string; sectionId: string }>();
  const courseId = params?.courseId;
  const sectionId = params?.sectionId;

  return (
    <div>
      <div className="mb-8">
        <Link
          href={`/analytics/${courseId}`}
          className="text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          ← Back to heatmap
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-foreground">
          Section Detail
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Affect breakdown, key insights, and content hotspots for this section
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface px-5 py-16 text-center">
        <p className="text-sm font-medium text-foreground">
          Section detail coming in Story 7.4
        </p>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          The affect bars, key insights, and content hotspot preview for section{" "}
          <code className="rounded bg-background/60 px-1.5 py-0.5 text-xs">
            {sectionId}
          </code>{" "}
          (course{" "}
          <code className="rounded bg-background/60 px-1.5 py-0.5 text-xs">
            {courseId}
          </code>
          ) will render here once Story 7.4 is implemented.
        </p>
      </div>
    </div>
  );
}
