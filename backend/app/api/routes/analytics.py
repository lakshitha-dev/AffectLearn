"""Analytics API endpoints (Story 7.1).

Designer/admin-only, read-only aggregation API for the course-designer analytics dashboard
(Epic 7). Routes stay thin: auth → resolve ids → delegate to `analytics_service` → shape the
camelCase response. All three are gated by `require_role(Role.course_designer, Role.admin)`
with `get_db` injected, mirroring the read-only discipline of `research.py`.

  - GET /api/v1/analytics/courses/{courseId}/overview        → CourseOverviewResponse
  - GET /api/v1/analytics/courses/{courseId}/affect-heatmap  → AffectHeatmapResponse
  - GET /api/v1/analytics/sections/{sectionId}/detail        → SectionDetailResponse
  - GET /api/v1/analytics/courses/{courseId}/effectiveness   → CourseEffectivenessResponse
  - GET /api/v1/analytics/courses/{courseId}/struggle        → StruggleLeaderboardResponse
  - GET /api/v1/analytics/sections/{sectionId}/questions     → SectionQuestionsResponse

The last three answer "what did learners DO here" rather than "how did they FEEL here". On a
paginated one-section-per-page reader that is the stronger evidence: going back to re-read,
revealing an answer and getting a question wrong need no model to interpret, and the platform has
been logging all three on every completion without anything reading them.

404 on unknown course/section (raised from the service); 403 for learners; 200 for
designer/admin. No writes, no migration.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.models.user import Role, User
from app.schemas.analytics import (
    AffectDistribution,
    AffectHeatmapResponse,
    CourseEffectivenessResponse,
    CourseOverviewResponse,
    HeatmapSectionRow,
    ParagraphAnnotation,
    SectionDetailResponse,
    SectionInsights,
    SectionQuestionsResponse,
    StruggleLeaderboardResponse,
    TemporalBin,
)
from app.services import analytics_service, content_effectiveness_service, course_ownership

router = APIRouter()


@router.get("/courses/{course_id}/overview", response_model=CourseOverviewResponse)
async def get_course_overview(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
) -> CourseOverviewResponse:
    """Aggregated course overview stats with sample-size + confidence indicators (AC1)."""
    await course_ownership.assert_can_view_course_analytics(db, current_user, course_id)
    data = await analytics_service.course_overview(db, course_id)
    return CourseOverviewResponse(**data)


@router.get("/courses/{course_id}/affect-heatmap", response_model=AffectHeatmapResponse)
async def get_affect_heatmap(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
) -> AffectHeatmapResponse:
    """Per-section affect distribution in course order, each row carrying confidence (AC2)."""
    await course_ownership.assert_can_view_course_analytics(db, current_user, course_id)
    data = await analytics_service.affect_heatmap(db, course_id)
    return AffectHeatmapResponse(
        course_id=data["course_id"],
        sections=[HeatmapSectionRow(**row) for row in data["sections"]],
    )


@router.get("/sections/{section_id}/detail", response_model=SectionDetailResponse)
async def get_section_detail(
    section_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
) -> SectionDetailResponse:
    """Section affect distribution, temporal bins, key insights, and annotated content (AC3)."""
    await course_ownership.assert_can_view_section_analytics(db, current_user, section_id)
    data = await analytics_service.section_detail(db, section_id)
    return SectionDetailResponse(
        section_id=data["section_id"],
        section_title=data["section_title"],
        affect_distribution=AffectDistribution(**data["affect_distribution"]),
        temporal_distribution=[TemporalBin(**b) for b in data["temporal_distribution"]],
        key_insights=SectionInsights(**data["key_insights"]),
        content=[
            ParagraphAnnotation(
                block_id=c["block_id"],
                paragraph_index=c["paragraph_index"],
                block_type=c["block_type"],
                text=c["text"],
                affect_distribution=(
                    AffectDistribution(**c["affect_distribution"])
                    if c["affect_distribution"] is not None
                    else None
                ),
            )
            for c in data["content"]
        ],
        sample_count=data["sample_count"],
        confidence=data["confidence"],
        insufficient_data=data["insufficient_data"],
    )


# ---------------------------------------------------------------------------
# Content effectiveness
# ---------------------------------------------------------------------------


@router.get("/courses/{course_id}/effectiveness", response_model=CourseEffectivenessResponse)
async def get_course_effectiveness(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    """Per-section behavioural evidence: dwell, revisits, answer reveals, wrong answers, and the
    help offered around them.

    Every rate can be null, and null is not zero. A section where no help was offered and one
    where help was offered but never followed by an attempt are different facts.
    """
    await course_ownership.assert_can_view_course_analytics(db, current_user, course_id)
    return await content_effectiveness_service.course_effectiveness(db, course_id)


@router.get("/courses/{course_id}/struggle", response_model=StruggleLeaderboardResponse)
async def get_struggle_leaderboard(
    course_id: uuid.UUID,
    limit: int = 5,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    """The sections learners struggle with most, worst first.

    Sections with too few observations are EXCLUDED rather than ranked low: a section completed
    twice can top any leaderboard by accident, and a designer acting on that would rewrite the
    wrong material.
    """
    await course_ownership.assert_can_view_course_analytics(db, current_user, course_id)
    sections = await content_effectiveness_service.struggle_leaderboard(
        db, course_id, limit=max(1, min(limit, 50))
    )
    return {"course_id": str(course_id), "sections": sections}


@router.get("/sections/{section_id}/questions", response_model=SectionQuestionsResponse)
async def get_section_questions(
    section_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    """Item analysis for a section's quiz blocks.

    `facility` is over all attempts; `firstAttemptFacility` is over each learner's first attempt
    only, which is the fairer measure of whether the material taught it — later attempts are
    contaminated by the feedback earlier ones gave.
    """
    await course_ownership.assert_can_view_section_analytics(db, current_user, section_id)
    return await content_effectiveness_service.section_questions(db, section_id)
