"""Sample pedagogical decisions for expert review, and score the agreement between reviewers.

WHAT THIS IS FOR

RQ3 currently reports Cohen's kappa 0.79 between the fine-tuned agent and the rule policy it was
trained on. That is a fidelity result. It says the model reproduces its training target, which
the surrounding graph can depend on, and says nothing about whether the decisions are
educationally sound -- an agent faithfully reproducing a bad policy scores identically.

Turning that into a pedagogical result needs qualified educators to rate real decisions against
a rubric. This module is the instrument.

THE SAMPLE MUST BE THE SAME FOR EVERYONE

Agreement between two reviewers is only defined over decisions they BOTH rated. If each reviewer
were handed a fresh random draw they would overlap by accident and the statistic would be
computed on whatever intersection happened to occur.

So the sample is deterministic: the oldest `sample_size` reviewable decisions, ordered by
`(created_at, id)`. Ordering ascending by creation time means new decisions are appended AFTER
the sample rather than shuffled into it, so the set stays fixed as the platform keeps running --
without needing a separate batch table to freeze it.

WHAT COUNTS AS REVIEWABLE

A decision with text a person can actually judge, that reached a learner. An undelivered offer or
a selective action with no prose gives a reviewer nothing to rate, and including them would pad
the denominator with items nobody could score.
"""

from __future__ import annotations

import uuid
from itertools import combinations
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistance_event import AssistanceEvent
from app.models.user import User
from app.models.decision_review import (
    RATING_MAX,
    RATING_MIN,
    RUBRIC_DIMENSIONS,
    DecisionReview,
)

logger = structlog.get_logger(__name__)

#: The default review set. The thesis specifies "fifty to a hundred pedagogical decisions rated
#: against a rubric by qualified educators"; 100 is the top of that range and is what the sample
#: is capped at unless a caller narrows it.
DEFAULT_SAMPLE_SIZE = 100
MAX_SAMPLE_SIZE = 500


class ValidationError(ValueError):
    """A submitted rating that cannot be stored as given."""


def _reviewable():
    """Decisions an educator can judge, from real learners only.

    Seeded demo accounts (`services/demo_scope.py`) are excluded: their hints were written for a
    demonstration, and rating them would put invented decisions into the agreement figures.
    """
    return (
        # Something a person can judge...
        AssistanceEvent.hint_text.isnot(None),
        AssistanceEvent.hint_text != "",
        # ...that actually reached a learner.
        AssistanceEvent.delivered_at.isnot(None),
        AssistanceEvent.learner_id.notin_(select(User.id).where(User.is_demo.is_(True))),
    )


def _sample_stmt(sample_size: int):
    """The deterministic review sample. See the module docstring for why it is not random."""
    return (
        select(AssistanceEvent)
        .where(*_reviewable())
        .order_by(AssistanceEvent.created_at.asc(), AssistanceEvent.id.asc())
        .limit(sample_size)
    )


async def sample_ids(db: AsyncSession, *, sample_size: int = DEFAULT_SAMPLE_SIZE) -> list[uuid.UUID]:
    rows = (await db.execute(_sample_stmt(sample_size))).scalars().all()
    return [row.id for row in rows]


def _presented(event: AssistanceEvent) -> dict[str, Any]:
    """One decision as a reviewer should see it.

    Deliberately omits `outcome_is_correct`. Knowing the learner went on to answer correctly
    would turn "was this a good decision" into "did it happen to work", and a reviewer told the
    outcome first cannot un-know it. The two questions are different and the second is not the
    one being asked.

    Also omits the learner identity. A reviewer judging pedagogy has no need for it.
    """
    return {
        "assistance_event_id": str(event.id),
        "action_type": event.action_type,
        "urgency": event.urgency,
        "hint_text": event.hint_text,
        # The system's own stated reason, shown so a reviewer can judge the REASONING and not
        # only the output -- the half a rubric on text alone would miss.
        "rationale": event.rationale,
        "affect_state": event.affect_state,
        "affect_source": event.affect_source,
        "affect_confidence": event.affect_confidence,
        "cycle_number": event.cycle_number,
        # Whether a model or the deterministic fallback wrote it. Shown because a review that
        # pooled the two would report a quality figure for "the agent" that is partly the rule
        # map's -- and production currently serves the fallback.
        "generated": bool(event.generated),
        "fallback_reason": event.fallback_reason,
    }


async def next_for_review(
    db: AsyncSession,
    *,
    reviewer_id: uuid.UUID,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
) -> dict[str, Any] | None:
    """The next decision this reviewer has not yet rated, or None when they are done."""
    ids = await sample_ids(db, sample_size=sample_size)
    if not ids:
        return None

    rated = set(
        (
            await db.execute(
                select(DecisionReview.assistance_event_id).where(
                    DecisionReview.reviewer_id == reviewer_id,
                    DecisionReview.assistance_event_id.in_(ids),
                )
            )
        ).scalars().all()
    )

    for event_id in ids:
        if event_id in rated:
            continue
        event = await db.get(AssistanceEvent, event_id)
        if event is None:
            continue
        return {
            **_presented(event),
            "reviewed_count": len(rated),
            "sample_size": len(ids),
        }
    return None


def _validate(ratings: Any) -> dict[str, int]:
    """Reject a rating that could not be analysed, rather than storing it and discovering later.

    A missing dimension is a partial review, and pooling partial reviews with complete ones makes
    a per-dimension mean silently computed over different denominators.
    """
    if not isinstance(ratings, dict):
        raise ValidationError("ratings must be an object")

    missing = [d for d in RUBRIC_DIMENSIONS if d not in ratings]
    if missing:
        raise ValidationError(f"missing rubric dimensions: {', '.join(missing)}")

    unknown = [k for k in ratings if k not in RUBRIC_DIMENSIONS]
    if unknown:
        raise ValidationError(f"unknown rubric dimensions: {', '.join(unknown)}")

    cleaned: dict[str, int] = {}
    for dimension in RUBRIC_DIMENSIONS:
        value = ratings[dimension]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError(f"{dimension} must be a whole number")
        if not RATING_MIN <= value <= RATING_MAX:
            raise ValidationError(f"{dimension} must be between {RATING_MIN} and {RATING_MAX}")
        cleaned[dimension] = value
    return cleaned


async def submit(
    db: AsyncSession,
    *,
    assistance_event_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    ratings: Any,
    would_make_same_call: bool,
    comment: str | None = None,
) -> DecisionReview:
    """Record one reviewer's rating. Commits. Raises `ValidationError` on a rating it cannot store.

    Re-submitting UPDATES rather than adding a second row: a reviewer correcting a slip should
    not be counted twice in every agreement statistic computed afterwards.
    """
    cleaned = _validate(ratings)

    existing = (
        await db.execute(
            select(DecisionReview).where(
                DecisionReview.assistance_event_id == assistance_event_id,
                DecisionReview.reviewer_id == reviewer_id,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.ratings = cleaned
        existing.would_make_same_call = bool(would_make_same_call)
        existing.comment = comment
        await db.commit()
        return existing

    review = DecisionReview(
        assistance_event_id=assistance_event_id,
        reviewer_id=reviewer_id,
        ratings=cleaned,
        would_make_same_call=bool(would_make_same_call),
        comment=comment,
        rubric_version={"version": 1, "dimensions": list(RUBRIC_DIMENSIONS)},
    )
    db.add(review)
    await db.commit()
    return review


def cohens_kappa(a: list[bool], b: list[bool]) -> float | None:
    """Cohen's kappa for two raters on the same binary items.

    Reported instead of raw agreement because raw agreement is inflated by the base rate: if
    ninety per cent of decisions are reasonable, two raters who both simply always said "yes"
    agree ninety per cent of the time while sharing no judgement at all. Kappa corrects for the
    agreement expected by chance.

    Returns None when it is undefined -- fewer than two items, or one rater giving a constant
    answer, which makes the expected agreement 1.0 and the denominator zero. A constant rater is
    a real and interesting finding; reporting it as kappa 0.0 would say "no better than chance",
    which is a different claim.
    """
    if len(a) != len(b) or len(a) < 2:
        return None

    n = len(a)
    observed = sum(1 for x, y in zip(a, b) if x == y) / n

    p_a_yes = sum(a) / n
    p_b_yes = sum(b) / n
    expected = p_a_yes * p_b_yes + (1 - p_a_yes) * (1 - p_b_yes)

    if expected >= 1.0:
        return None
    return round((observed - expected) / (1 - expected), 4)


async def summary(
    db: AsyncSession, *, sample_size: int = DEFAULT_SAMPLE_SIZE
) -> dict[str, Any]:
    """Progress, per-dimension means, and pairwise agreement between reviewers.

    Agreement is reported PER PAIR rather than pooled into one number. With a handful of
    reviewers a pooled figure hides that one of them disagrees with everyone, which is the
    finding most worth acting on -- it usually means the rubric is ambiguous rather than that
    the rater is wrong.
    """
    ids = await sample_ids(db, sample_size=sample_size)
    if not ids:
        return {
            "sample_size": 0,
            "reviews_submitted": 0,
            "reviewer_count": 0,
            "decisions_with_any_review": 0,
            "dimension_means": {d: None for d in RUBRIC_DIMENSIONS},
            "would_make_same_call_rate": None,
            "pairwise_agreement": [],
        }

    reviews = (
        await db.execute(
            select(DecisionReview).where(DecisionReview.assistance_event_id.in_(ids))
        )
    ).scalars().all()

    by_reviewer: dict[uuid.UUID, dict[uuid.UUID, DecisionReview]] = {}
    for review in reviews:
        by_reviewer.setdefault(review.reviewer_id, {})[review.assistance_event_id] = review

    dimension_means: dict[str, float | None] = {}
    for dimension in RUBRIC_DIMENSIONS:
        values = [
            r.ratings[dimension]
            for r in reviews
            if isinstance(r.ratings, dict) and isinstance(r.ratings.get(dimension), int)
        ]
        dimension_means[dimension] = round(sum(values) / len(values), 2) if values else None

    same_call = [r.would_make_same_call for r in reviews]

    pairwise: list[dict[str, Any]] = []
    for left, right in combinations(sorted(by_reviewer, key=str), 2):
        shared = sorted(set(by_reviewer[left]) & set(by_reviewer[right]), key=str)
        if not shared:
            continue
        a = [by_reviewer[left][i].would_make_same_call for i in shared]
        b = [by_reviewer[right][i].would_make_same_call for i in shared]
        pairwise.append(
            {
                "reviewer_a": str(left),
                "reviewer_b": str(right),
                "shared_decisions": len(shared),
                "raw_agreement": round(
                    sum(1 for x, y in zip(a, b) if x == y) * 100.0 / len(shared), 1
                ),
                "cohens_kappa": cohens_kappa(a, b),
            }
        )

    return {
        "sample_size": len(ids),
        "reviews_submitted": len(reviews),
        "reviewer_count": len(by_reviewer),
        "decisions_with_any_review": len({r.assistance_event_id for r in reviews}),
        "dimension_means": dimension_means,
        "would_make_same_call_rate": (
            round(sum(same_call) * 100.0 / len(same_call), 1) if same_call else None
        ),
        "pairwise_agreement": pairwise,
    }


async def reviewable_total(db: AsyncSession) -> int:
    """How many decisions exist that could be reviewed, regardless of the sample cap.

    Surfaced so a coordinator can tell "the sample is exhausted" from "the platform has produced
    almost nothing to review" -- which, before a pilot, is the likely case.
    """
    return int(
        (
            await db.execute(
                select(func.count(AssistanceEvent.id)).where(*_reviewable())
            )
        ).scalar_one()
        or 0
    )
