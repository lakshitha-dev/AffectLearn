"""An educator's rating of one pedagogical decision the system made (migration 026).

WHY THIS EXISTS

The pedagogical agent's reported quality is Cohen's kappa 0.79 against the rule policy it was
trained on. That measures FIDELITY, not pedagogy: an agent faithfully reproducing a bad policy
would score exactly the same. Nothing in the project has ever asked a qualified educator whether
the decisions are any good.

The thesis names this as the highest-value outstanding work per hour invested, and notes that it
does not depend on the pilot at all -- the decisions already exist, or can be generated. This is
the instrument for collecting it.

WHY THE RATINGS ARE STORED PER REVIEWER RATHER THAN AVERAGED

Inter-rater agreement is the point. An average discards exactly the disagreement that tells you
whether the rubric means the same thing to two people, and a rubric nobody agrees on produces a
quality score that is really a measure of who was asked.

INDEPENDENCE

One row per (reviewer, decision), enforced by a unique constraint. Nothing in the read path shows
a reviewer what anyone else scored: seeing another rating first makes the second one partly a
measure of the first, and the agreement statistic then flatters itself.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import BaseModel

#: The rubric, fixed here so every reviewer scores the same dimensions and a later analysis can
#: report them separately. Each is 1-5.
#:
#: Chosen to separate the two failures that look identical in an overall score: a well-written
#: hint offered at the wrong moment, and a badly written hint offered at the right one. An agent
#: can be good at one and poor at the other, and a single number hides which.
RUBRIC_DIMENSIONS: tuple[str, ...] = (
    # Was intervening the right call here at all, given the learner's state?
    "appropriateness",
    # Was this the right MOMENT -- not too early to have struggled, not long after giving up?
    "timing",
    # Is the content itself accurate and pitched correctly for the material?
    "quality",
    # Does it help the learner reason, rather than handing over the answer?
    "restraint",
)

RATING_MIN = 1
RATING_MAX = 5


class DecisionReview(BaseModel):
    __tablename__ = "decision_reviews"
    __table_args__ = (
        # One rating per reviewer per decision. A reviewer who could rate the same decision twice
        # would weight themselves in every agreement statistic computed afterwards.
        UniqueConstraint("assistance_event_id", "reviewer_id", name="uq_decision_review"),
    )

    assistance_event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assistance_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: `{dimension: 1..5}` for each of `RUBRIC_DIMENSIONS`. JSON rather than four columns so a
    #: rubric revision does not need a migration; the vocabulary is validated in the service, and
    #: `rubric_version` says which vocabulary a row was scored against.
    ratings = Column(JSON, nullable=False)
    #: The headline judgement, kept separate from the dimensions on purpose. "Would you have made
    #: this call?" is the question a teacher can answer without a rubric, and it is the one an
    #: agreement statistic is most interpretable on.
    would_make_same_call = Column(Boolean, nullable=False)
    comment = Column(Text, nullable=True)
    #: Bumped when `RUBRIC_DIMENSIONS` changes meaning, so ratings from two vintages are never
    #: pooled into one agreement figure without someone deciding to.
    rubric_version = Column(JSON, nullable=False, default=lambda: {"version": 1})
    submitted_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
