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

/**
 * The four affect states surfaced on the designer heatmap (Story 7.3). These are
 * the DESIGNER palette only — never shown to learners (UX spec line 403).
 */
export type AffectState = "engaged" | "confused" | "bored" | "frustrated";

/**
 * One section row in the affect heatmap (Story 7.3).
 *
 * Mirrors the backend `HeatmapSectionRow` (`app/schemas/analytics.py`, camelCase
 * via `CamelModel`) field-for-field. Each `*Pct` is a 0-100 float on a
 * PER-LEARNER basis (the share of observed learners who showed that state), so
 * the four values MAY sum to >100 — a learner can show multiple states. Do NOT
 * normalize. Rows arrive already ordered by course position (module → lesson →
 * section sortOrder); render top-to-bottom as received (do NOT re-sort).
 */
export interface HeatmapSectionRow {
  sectionId: string;
  sectionTitle: string;
  engagedPct: number;
  confusedPct: number;
  boredPct: number;
  frustratedPct: number;
  sampleCount: number;
  confidence: Confidence;
  insufficientData: boolean;
}

/**
 * `GET /analytics/courses/{courseId}/affect-heatmap` payload.
 *
 * Mirrors `AffectHeatmapResponse` (app/schemas/analytics.py). An empty course
 * returns `sections: []`; a section with zero observed learners returns zeros +
 * `insufficientData: true`.
 */
export interface AffectHeatmapResponse {
  courseId: string;
  sections: HeatmapSectionRow[];
}
