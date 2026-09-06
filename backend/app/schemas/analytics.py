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


# ---------------------------------------------------------------------------
# Content effectiveness
#
# Every rate here is `float | None`, deliberately. Zero and unknown are different facts: a
# section where no help was ever offered and one where help was offered and never followed by an
# attempt both have "no outcome rate", and returning 0.0 for both would say help never works
# there. The UI renders null as "—" rather than as a number.
# ---------------------------------------------------------------------------


class SectionAssistance(CamelModel):
    """What help was offered in a section, and what happened around it."""

    offers: int
    learners_helped: int
    dismissal_rate: float | None = None
    #: Share of delivered help written by the model rather than the deterministic fallback.
    #: Expected to be low while production has no GPU quota — hiding it would report the
    #: fine-tuned agent's behaviour while showing the fallback's.
    generated_rate: float | None = None
    #: Share of FOLLOWED-UP offers where the learner's next attempt was correct.
    #:
    #: An ASSOCIATION, not a causal claim: the learner may have solved it despite the hint or
    #: ignored it entirely. Denominator is offers that were followed by an attempt, not all
    #: offers — help never followed up is unknown, not failed.
    followed_by_correct_rate: float | None = None
    outcomes_recorded: int


class SectionEffectivenessRow(CamelModel):
    """One section's behavioural evidence, in course order."""

    section_id: str
    section_title: str
    observed_learners: int
    time_on_section_s: float | None = None
    time_per_100_words: float | None = None
    back_nav_count: float | None = None
    quiz_attempt_count: float | None = None
    quiz_incorrect_count: float | None = None
    quiz_response_time_ms_mean: float | None = None
    show_answer_used_rate: float | None = None
    revisit_rate: float | None = None
    quiz_incorrect_rate: float | None = None
    assistance: SectionAssistance
    confidence: Confidence
    insufficient_data: bool


class CourseEffectivenessResponse(CamelModel):
    """`GET /analytics/courses/{courseId}/effectiveness` payload."""

    course_id: str
    sections: list[SectionEffectivenessRow]


class StruggleRow(SectionEffectivenessRow):
    """A leaderboard row: a section plus its composite struggle score."""

    struggle_score: float


class StruggleLeaderboardResponse(CamelModel):
    """`GET /analytics/courses/{courseId}/struggle` payload."""

    course_id: str
    sections: list[StruggleRow]


class QuestionDifficultyRow(CamelModel):
    """Item analysis for one quiz block."""

    block_id: str
    question: str | None = None
    attempts: int
    learners: int
    #: Share of ALL attempts that were correct — the classic p-value, low meaning hard.
    facility: float | None = None
    #: The same figure restricted to each learner's FIRST attempt, which is the fairer measure of
    #: whether the material taught it: later attempts are contaminated by earlier feedback.
    first_attempt_facility: float | None = None
    mean_attempts_per_learner: float | None = None
    mean_response_time_ms: float | None = None
    attempts_with_help_on_screen: int
    confidence: Confidence
    insufficient_data: bool


class SectionQuestionsResponse(CamelModel):
    """`GET /analytics/sections/{sectionId}/questions` payload."""

    section_id: str
    questions: list[QuestionDifficultyRow]
