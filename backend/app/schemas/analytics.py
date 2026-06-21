"""Analytics response schemas (Story 7.1).

camelCase (`CamelModel`) response contracts for the designer/admin analytics dashboard
(Epic 7). These are the stable shapes the frontend stories 7.2 (overview), 7.3 (heatmap),
and 7.4 (section detail) bind to. All percentages are 0-100 floats; `confidence` is a
stable `low|medium|high` literal driven by the single-source `_confidence` helper in
`app/services/analytics_service.py`.
"""

from __future__ import annotations

from typing import Literal

from app.schemas.base import CamelModel

Confidence = Literal["low", "medium", "high"]


class AffectDistribution(CamelModel):
    """Per-affect percentage breakdown on a per-LEARNER basis (AC2): each value is the share
    of observed learners who showed that affect state. Values can sum to >100 because a
    learner may show multiple states; each is 0-100."""

    engaged_pct: float
    confused_pct: float
    bored_pct: float
    frustrated_pct: float


class CourseOverviewResponse(CamelModel):
    """`GET /analytics/courses/{courseId}/overview` payload."""

    course_id: str
    total_learners: int
    completion_rate: float  # 0-100
    average_engagement_score: float  # 0-100 (engaged share of observations)
    confusion_hotspot_count: int
    sample_count: int
    confidence: Confidence
    insufficient_data: bool


class HeatmapSectionRow(CamelModel):
    """One section row in the affect heatmap (course-ordered)."""

    section_id: str
    section_title: str
    engaged_pct: float
    confused_pct: float
    bored_pct: float
    frustrated_pct: float
    sample_count: int
    confidence: Confidence
    insufficient_data: bool


class AffectHeatmapResponse(CamelModel):
    """`GET /analytics/courses/{courseId}/affect-heatmap` payload."""

    course_id: str
    sections: list[HeatmapSectionRow]


class TemporalBin(CamelModel):
    """One temporal bin of within-section confusion share (best-effort)."""

    bin_index: int
    confused_pct: float


class SectionInsights(CamelModel):
    """Best-effort key insights for a section (AC3), derived from research_events scoped to
    the section's learners. Only the two AC-contract fields are exposed."""

    most_triggered_adaptation_type: str | None = None
    average_confusion_duration_seconds: float | None = None


class ParagraphAnnotation(CamelModel):
    """A content block rendered read-only with a (section-level) affect annotation.

    Paragraph-precise affect is not logged today, so `affect_distribution` carries the
    section-level distribution where derivable, else null. See `analytics_service`.
    """

    block_id: str
    paragraph_index: int
    block_type: str
    text: str | None = None
    affect_distribution: AffectDistribution | None = None


class SectionDetailResponse(CamelModel):
    """`GET /analytics/sections/{sectionId}/detail` payload."""

    section_id: str
    section_title: str
    affect_distribution: AffectDistribution
    temporal_distribution: list[TemporalBin]
    key_insights: SectionInsights
    content: list[ParagraphAnnotation]
    sample_count: int
    confidence: Confidence
    insufficient_data: bool
