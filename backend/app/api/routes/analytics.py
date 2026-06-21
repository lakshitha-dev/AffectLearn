"""Analytics API endpoints (Story 7.1).

Designer/admin-only, read-only aggregation API for the course-designer analytics dashboard
(Epic 7). Routes stay thin: auth → resolve ids → delegate to `analytics_service` → shape the
camelCase response. All three are gated by `require_role(Role.course_designer, Role.admin)`
with `get_db` injected, mirroring the read-only discipline of `research.py`.

  - GET /api/v1/analytics/courses/{courseId}/overview        → CourseOverviewResponse
  - GET /api/v1/analytics/courses/{courseId}/affect-heatmap  → AffectHeatmapResponse
  - GET /api/v1/analytics/sections/{sectionId}/detail        → SectionDetailResponse

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
    CourseOverviewResponse,
    HeatmapSectionRow,
    ParagraphAnnotation,
    SectionDetailResponse,
    SectionInsights,
    TemporalBin,
)
from app.services import analytics_service

router = APIRouter()


@router.get("/courses/{course_id}/overview", response_model=CourseOverviewResponse)
async def get_course_overview(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(Role.course_designer, Role.admin)),
) -> CourseOverviewResponse:
    """Aggregated course overview stats with sample-size + confidence indicators (AC1)."""
    data = await analytics_service.course_overview(db, course_id)
    return CourseOverviewResponse(**data)


@router.get("/courses/{course_id}/affect-heatmap", response_model=AffectHeatmapResponse)
async def get_affect_heatmap(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(Role.course_designer, Role.admin)),
) -> AffectHeatmapResponse:
    """Per-section affect distribution in course order, each row carrying confidence (AC2)."""
    data = await analytics_service.affect_heatmap(db, course_id)
    return AffectHeatmapResponse(
        course_id=data["course_id"],
        sections=[HeatmapSectionRow(**row) for row in data["sections"]],
    )


@router.get("/sections/{section_id}/detail", response_model=SectionDetailResponse)
async def get_section_detail(
    section_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(Role.course_designer, Role.admin)),
) -> SectionDetailResponse:
    """Section affect distribution, temporal bins, key insights, and annotated content (AC3)."""
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
