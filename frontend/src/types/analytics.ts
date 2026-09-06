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

/**
 * Per-affect percentage breakdown (Story 7.4 section detail).
 *
 * Mirrors the backend `AffectDistribution` (`app/schemas/analytics.py`). Each
 * `*Pct` is a 0-100 float on a PER-LEARNER basis (the share of observed learners
 * who showed that state), so the four values MAY sum to >100 — a learner can show
 * multiple states. Do NOT normalize to a single 100% stacked bar.
 */
export interface AffectDistribution {
  engagedPct: number;
  confusedPct: number;
  boredPct: number;
  frustratedPct: number;
}

/**
 * One temporal bin of within-section confusion share (Story 7.4).
 *
 * Mirrors the backend `TemporalBin`. The temporal distribution is SECTION-LEVEL
 * and best-effort (session-concatenated cycle order, NOT a true chronological
 * timeline — see 7.1) — there is no per-paragraph temporal data.
 */
export interface TemporalBin {
  binIndex: number;
  confusedPct: number;
}

/**
 * Best-effort key insights for a section (Story 7.4).
 *
 * Mirrors the backend `SectionInsights` field-for-field. ONLY these two fields
 * are returned: the "% who needed hints" / "% who took breaks" insights from the
 * original epic AC text were REMOVED from the backend schema during the 7.1
 * Senior Developer Review (no honest section-scoped source existed). Do NOT add
 * them. Both fields are nullable.
 */
export interface SectionInsights {
  mostTriggeredAdaptationType: string | null;
  averageConfusionDurationSeconds: number | null;
}

/**
 * A content block rendered read-only with a (section-level) affect annotation
 * (Story 7.4). Mirrors the backend `ParagraphAnnotation`.
 *
 * Paragraph-precise affect is NOT logged today: `affectDistribution` carries the
 * SECTION-LEVEL distribution where derivable (`sampleCount > 0`), else `null`. So
 * multiple hotspot blocks will share the same section-level numbers — surface
 * this honestly, do NOT imply per-paragraph precision. `text` is the extracted
 * block text only (NOT the full original `content` object).
 */
export interface ParagraphAnnotation {
  blockId: string;
  paragraphIndex: number;
  blockType: string;
  text: string | null;
  affectDistribution: AffectDistribution | null;
}

/**
 * `GET /analytics/sections/{sectionId}/detail` payload (Story 7.4).
 *
 * Mirrors `SectionDetailResponse` (`app/schemas/analytics.py`). Section-keyed
 * only — it returns NO `moduleId`/`lessonId` for the section's parent lesson, so
 * "Edit Content" cannot deep-link the exact lesson editor (see the page).
 */
export interface SectionDetailResponse {
  sectionId: string;
  sectionTitle: string;
  affectDistribution: AffectDistribution;
  temporalDistribution: TemporalBin[];
  keyInsights: SectionInsights;
  content: ParagraphAnnotation[];
  sampleCount: number;
  confidence: Confidence;
  insufficientData: boolean;
}

/* ------------------------------------------------------------------ */
/* Content effectiveness                                               */
/*                                                                     */
/* Every rate is `number | null`. Null is not zero: a section where no  */
/* help was offered and one where help was offered but never followed  */
/* by an attempt both have "no outcome rate", and rendering both as 0   */
/* would tell a designer that help never works there.                  */
/* ------------------------------------------------------------------ */

export interface SectionAssistance {
  offers: number;
  learnersHelped: number;
  dismissalRate: number | null;
  /**
   * Share of delivered help written by the model rather than the rule fallback. Production has
   * no GPU quota, so this is expected to be low — hiding it would report the fine-tuned agent's
   * behaviour while showing the fallback's.
   */
  generatedRate: number | null;
  /**
   * Share of FOLLOWED-UP offers where the learner's next attempt was correct.
   *
   * An association, not a cause. The learner may have solved it despite the hint or ignored it.
   * Anything rendering this must say which of the two it is asserting.
   */
  followedByCorrectRate: number | null;
  outcomesRecorded: number;
}

export interface SectionEffectivenessRow {
  sectionId: string;
  sectionTitle: string;
  observedLearners: number;
  timeOnSectionS: number | null;
  timePer100Words: number | null;
  backNavCount: number | null;
  quizAttemptCount: number | null;
  quizIncorrectCount: number | null;
  quizResponseTimeMsMean: number | null;
  showAnswerUsedRate: number | null;
  revisitRate: number | null;
  quizIncorrectRate: number | null;
  assistance: SectionAssistance;
  confidence: "low" | "medium" | "high";
  insufficientData: boolean;
}

export interface CourseEffectivenessResponse {
  courseId: string;
  sections: SectionEffectivenessRow[];
}

export interface StruggleRow extends SectionEffectivenessRow {
  struggleScore: number;
}

export interface StruggleLeaderboardResponse {
  courseId: string;
  sections: StruggleRow[];
}

export interface QuestionDifficultyRow {
  blockId: string;
  question: string | null;
  attempts: number;
  learners: number;
  /** Share of ALL attempts correct — the classic p-value, low meaning hard. */
  facility: number | null;
  /** The same over each learner's FIRST attempt only, uncontaminated by earlier feedback. */
  firstAttemptFacility: number | null;
  meanAttemptsPerLearner: number | null;
  meanResponseTimeMs: number | null;
  attemptsWithHelpOnScreen: number;
  confidence: "low" | "medium" | "high";
  insufficientData: boolean;
}

export interface SectionQuestionsResponse {
  sectionId: string;
  questions: QuestionDifficultyRow[];
}
