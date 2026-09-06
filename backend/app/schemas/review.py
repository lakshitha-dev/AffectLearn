"""Expert-review API schemas.

`DecisionForReview` deliberately omits two things a reviewer must not see:

* THE OUTCOME. Knowing the learner went on to answer correctly turns "was this a good decision"
  into "did it happen to work", and a reviewer told the outcome first cannot un-know it.
* OTHER REVIEWERS' RATINGS. Seeing another score first makes this one partly a measure of that
  one, and the agreement statistic then flatters itself.
"""

from __future__ import annotations

import uuid

from app.schemas.base import CamelModel


class RubricResponse(CamelModel):
    """The dimensions and scale, served rather than hardcoded in the client."""

    dimensions: list[str]
    min_rating: int
    max_rating: int


class DecisionForReview(CamelModel):
    """One pedagogical decision as a reviewer sees it."""

    assistance_event_id: str
    action_type: str
    urgency: str | None = None
    hint_text: str | None = None
    #: The system's own stated reason. Shown so a reviewer can judge the REASONING and not only
    #: the output — the half a rubric applied to text alone would miss.
    rationale: str | None = None
    affect_state: str | None = None
    affect_source: str | None = None
    affect_confidence: float | None = None
    cycle_number: int
    #: Whether a model or the deterministic fallback wrote this. Shown because a review pooling
    #: the two would report a quality figure for "the agent" that is partly the rule map's — and
    #: production currently serves the fallback.
    generated: bool
    fallback_reason: str | None = None
    #: Progress, so a reviewer can see how much is left.
    reviewed_count: int
    sample_size: int


class ReviewSubmission(CamelModel):
    """One reviewer's rating of one decision."""

    assistance_event_id: uuid.UUID
    #: `{dimension: 1..5}` for every dimension the rubric endpoint lists. Validated server-side:
    #: a partial review pooled with complete ones makes a per-dimension mean computed over
    #: silently different denominators.
    ratings: dict[str, int]
    #: The headline judgement, kept apart from the rubric on purpose. "Would you have made this
    #: call?" is answerable without a rubric and is the item agreement is most interpretable on.
    would_make_same_call: bool
    comment: str | None = None


class ReviewSubmitted(CamelModel):
    id: str


class PairwiseAgreement(CamelModel):
    """Agreement between two reviewers over the decisions they BOTH rated."""

    reviewer_a: str
    reviewer_b: str
    shared_decisions: int
    raw_agreement: float
    #: Null when undefined — fewer than two shared items, or a rater who gave a constant answer,
    #: which makes expected agreement 1.0 and the denominator zero. A constant rater is a real
    #: finding; reporting it as 0.0 would say "no better than chance", a different claim.
    cohens_kappa: float | None = None


class ReviewSummary(CamelModel):
    """`GET /reviews/summary` payload."""

    sample_size: int
    #: Reviewable decisions in existence, regardless of the sample cap. Distinguishes "the sample
    #: is exhausted" from "the platform has produced almost nothing to review", which before a
    #: pilot is the likely case.
    reviewable_total: int = 0
    reviews_submitted: int
    reviewer_count: int
    decisions_with_any_review: int
    dimension_means: dict[str, float | None]
    would_make_same_call_rate: float | None = None
    pairwise_agreement: list[PairwiseAgreement]
