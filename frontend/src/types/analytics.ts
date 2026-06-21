/**
 * Analytics response types (Epic 7 — designer analytics dashboard).
 *
 * camelCase shapes mirroring the backend `CamelModel` contracts in
 * `app/schemas/analytics.py` (Story 7.1). Story 7.2 consumes `CourseOverview`;
 * 7.3 (heatmap) and 7.4 (section detail) will extend this module.
 *
 * IMPORTANT: do NOT add fields the backend does not return. The overview
 * endpoint is PER-COURSE (`GET /analytics/courses/{courseId}/overview`); there
 * is no cross-course rollup.
 */

/** Confidence band for an aggregate, driven by the backend `_confidence` helper. */
export type Confidence = "low" | "medium" | "high";

/**
 * `GET /analytics/courses/{courseId}/overview` payload.
 *
 * Mirrors `CourseOverviewResponse` (app/schemas/analytics.py). `completionRate`
 * and `averageEngagementScore` are 0-100 floats (engagement = engaged share of
 * observations). `confidence`/`sampleCount`/`insufficientData` drive the honest
 * "limited data" indicator on the dashboard cards (there is NO period-over-period
 * trend in the contract).
 */
export interface CourseOverview {
  courseId: string;
  totalLearners: number;
  completionRate: number;
  averageEngagementScore: number;
  confusionHotspotCount: number;
  sampleCount: number;
  confidence: Confidence;
  insufficientData: boolean;
}
