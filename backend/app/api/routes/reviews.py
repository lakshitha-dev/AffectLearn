"""Expert review of pedagogical decisions.

RQ3 reports Cohen's kappa 0.79 between the fine-tuned agent and the rule policy it was trained
on. That is fidelity, not pedagogy — an agent faithfully reproducing a bad policy scores the
same. These endpoints are the instrument for asking qualified educators whether the decisions are
actually sound, which the thesis names as the highest-value outstanding work per hour invested
and which does not depend on the pilot.

  - GET  /api/v1/reviews/next     → the next decision this reviewer has not rated
  - POST /api/v1/reviews          → submit a rating
  - GET  /api/v1/reviews/summary  → progress, per-dimension means, pairwise agreement

Open to `course_designer` and `admin`: course designers are the educators on this platform, and
requiring an admin account to rate a hint would mean either handing out admin or transcribing
ratings by hand.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.models.decision_review import RATING_MAX, RATING_MIN, RUBRIC_DIMENSIONS
from app.models.user import Role, User
from app.schemas.review import (
    DecisionForReview,
    ReviewSubmission,
    ReviewSubmitted,
    ReviewSummary,
    RubricResponse,
)
from app.services import decision_review_service

router = APIRouter()


@router.get("/reviews/rubric", response_model=RubricResponse, tags=["reviews"])
async def get_rubric(
    _user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    """The rubric, served rather than duplicated in the client.

    A reviewer scoring dimensions the server does not know about, or missing one it requires,
    produces a partial review — and pooling partial reviews with complete ones makes a
    per-dimension mean computed over silently different denominators.
    """
    return RubricResponse(
        dimensions=list(RUBRIC_DIMENSIONS), min_rating=RATING_MIN, max_rating=RATING_MAX
    )


@router.get("/reviews/next", response_model=DecisionForReview | None, tags=["reviews"])
async def next_decision(
    sample_size: int = Query(
        default=decision_review_service.DEFAULT_SAMPLE_SIZE,
        ge=1,
        le=decision_review_service.MAX_SAMPLE_SIZE,
        alias="sampleSize",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    """The next decision in the review sample this reviewer has not yet rated, or null.

    The sample is deterministic — the oldest N reviewable decisions — so every reviewer rates the
    same set. Agreement between two reviewers is only defined over decisions they both saw, and a
    fresh random draw per reviewer would leave that to chance.
    """
    return await decision_review_service.next_for_review(
        db, reviewer_id=current_user.id, sample_size=sample_size
    )


@router.post(
    "/reviews",
    response_model=ReviewSubmitted,
    status_code=status.HTTP_201_CREATED,
    tags=["reviews"],
)
async def submit_review(
    body: ReviewSubmission,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    """Record this reviewer's rating of one decision.

    Re-submitting updates the existing rating rather than adding a second: a reviewer correcting
    a slip must not be counted twice in every agreement statistic computed afterwards.
    """
    try:
        review = await decision_review_service.submit(
            db,
            assistance_event_id=body.assistance_event_id,
            reviewer_id=current_user.id,
            ratings=body.ratings,
            would_make_same_call=body.would_make_same_call,
            comment=body.comment,
        )
    except decision_review_service.ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "INVALID_RATING", "message": str(exc)}},
        ) from exc

    return ReviewSubmitted(id=str(review.id))


@router.get("/reviews/summary", response_model=ReviewSummary, tags=["reviews"])
async def review_summary(
    sample_size: int = Query(
        default=decision_review_service.DEFAULT_SAMPLE_SIZE,
        ge=1,
        le=decision_review_service.MAX_SAMPLE_SIZE,
        alias="sampleSize",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    """Progress and agreement across reviewers.

    Agreement is reported per PAIR rather than pooled: with a handful of reviewers a single
    number hides that one of them disagrees with everyone, which is the finding most worth
    acting on — it usually means the rubric is ambiguous rather than that the rater is wrong.
    """
    data = await decision_review_service.summary(db, sample_size=sample_size)
    data["reviewable_total"] = await decision_review_service.reviewable_total(db)
    return data

