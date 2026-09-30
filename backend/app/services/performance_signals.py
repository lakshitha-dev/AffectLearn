"""A struggle reading taken from what the learner is DOING, not from a model of how they look.

WHY THIS CHANNEL EXISTS

The two detectors the platform ships are both weak on this particular interface, and the code
says so itself.

`section_features` records that the behavioural model is "structurally blind on this UI": four of
its sixteen features are scroll-based, the lesson page shows ONE SECTION PER PAGE with next/prev
navigation, and a learner barely scrolls. Measured live, two scroll events per thirty-second
window and P(confused) = 0.008 while the author was deliberately trying to appear confused. Its
training corpus was business software users, not learners.

The facial CNN channel fares no better in deployment: Chapter 4 records its live scores
compressing into a 0.127-wide band around its own threshold, which is why it was demoted to
advisory.

So the adaptive arm of a study risks being adaptive in name only -- a gate that almost never
opens is indistinguishable, from the learner's side, from the control condition.

Meanwhile the signals that DO discriminate on a paginated reader are sitting in the client
already: going back to re-read, revealing an answer rather than attempting it, getting a question
wrong repeatedly, dwelling far beyond what the text length warrants. `section_features` computes
all of them, and nothing has ever acted on them.

WHAT THIS IS AND IS NOT

It is a heuristic, and it is called one. The weights below are chosen for face validity, NOT
fitted -- there is no outcome data to fit them against, and presenting a tuned-looking number
without one would be false precision. Every weight is stated in the open so a reader can disagree
with a specific number rather than with an opaque score.

Its honesty is of a different kind from a model's. A model's confidence is a calibrated
probability that can be wrong in ways nobody can see. This says "the learner went back twice,
revealed an answer, and got the question wrong three times", and that is simply true. What
remains arguable is whether those things mean the learner is struggling -- which is a question a
reader can weigh for themselves.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

#: Provenance marker, matching the vocabulary in `agents.state`.
AFFECT_SOURCE_PERFORMANCE = "performance"

#: The state this channel reports. Confusion only, deliberately: wrong answers and re-reading are
#: evidence of not understanding. They say nothing about boredom -- a bored learner clicks
#: onward, producing exactly no struggle indicators -- and claiming otherwise would repeat the
#: mistake of listing states no detector can see.
PERFORMANCE_STATE = "confused"

# --- weights -------------------------------------------------------------------------------
#
# Chosen, not fitted. Ordered by how directly each indicates "did not understand this":
#
#   * A wrong answer is the most direct evidence available. Weighted highest, and saturating at
#     three so one badly-worded question cannot dominate.
#   * Revealing the answer is an admission of being stuck, and it is deliberate rather than
#     incidental -- which makes it a cleaner signal than any timing measure.
#   * Going back to re-read is the paginated equivalent of scrolling up. Strong, but it also
#     catches a learner simply checking a definition, so it is weighted below the first two.
#   * Dwelling is the weakest: a learner who leaves the tab open to make tea looks identical to
#     one labouring over a paragraph. It contributes least and saturates soonest.
_WEIGHT_INCORRECT = 0.35
_WEIGHT_SHOW_ANSWER = 0.25
_WEIGHT_BACK_NAV = 0.20
_WEIGHT_SLOW_PACE = 0.20

#: Counts at which each indicator stops adding. Saturation matters more than the weights: without
#: it, one learner rattling through a ten-question section would score higher than one genuinely
#: stuck on a two-question one.
#:
#: Wrong answers saturate at the section's own number of quizzes, capped at three, when that is
#: known. Each quiz takes one answer (`QuizBlock` locks after a submission) and most sections have
#: one quiz, so a fixed cap of three made one wrong answer on a section's only question worth a
#: third of the weight, and the channel could almost never reach an actionable score.
_INCORRECT_SATURATES_AT = 3
_BACK_NAV_SATURATES_AT = 3

#: Seconds per 100 words above which reading counts as slow, and the point at which "slow" stops
#: getting worse. A hundred words takes a comfortable reader roughly 25-30 seconds; 75 is well
#: past deliberate re-reading, and 200 is where the learner has almost certainly stopped reading
#: at all -- which is why the scale ends there rather than climbing forever.
_SLOW_PACE_THRESHOLD_S = 75.0
_SLOW_PACE_SATURATES_AT_S = 200.0

#: Below this the reading is reported but is not worth acting on. Chosen, not calibrated: it sits
#: where at least two independent indicators must be present, so no single measure can trigger an
#: intervention on its own.
MIN_ACTIONABLE_SCORE = 0.45


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def struggle_score(
    signals: Any, *, section_words: int | None = None, section_quizzes: int | None = None
) -> dict[str, Any]:
    """Score how much a learner appears to be struggling with the section they are on.

    Returns the score, the per-indicator contributions that produced it, and the counts behind
    them. The breakdown is returned rather than only the total because a bare number invites
    exactly the treatment this channel is meant to avoid -- an opaque confidence nobody can
    argue with. A reader can see that the score came from two wrong answers and a re-read.

    `section_quizzes` is how many quizzes the section has; wrong answers saturate there (at least
    one, at most three). Unknown keeps the fixed cap of three.

    Pure and total: never raises, whatever the client sends.
    """
    data = signals if isinstance(signals, dict) else {}

    incorrect = _as_int(data.get("quiz_incorrect_count"))
    back_nav = _as_int(data.get("back_nav_count"))
    show_answer = bool(data.get("show_answer_used"))
    seconds = _as_float(data.get("time_on_section_s"))
    incorrect_cap = (
        min(max(_as_int(section_quizzes), 1), _INCORRECT_SATURATES_AT)
        if section_quizzes is not None else _INCORRECT_SATURATES_AT
    )

    contributions: dict[str, float] = {
        "incorrect_answers": _WEIGHT_INCORRECT
        * _clamp(incorrect / incorrect_cap),
        "revealed_answer": _WEIGHT_SHOW_ANSWER if show_answer else 0.0,
        "back_navigation": _WEIGHT_BACK_NAV * _clamp(back_nav / _BACK_NAV_SATURATES_AT),
        "slow_pace": 0.0,
    }

    # Pace only when there is a word count to normalise by. Without one there is no denominator,
    # and inventing one would make a long section look like a struggling learner.
    pace_s_per_100 = None
    if section_words and section_words > 0 and seconds > 0:
        pace_s_per_100 = seconds / section_words * 100.0
        if pace_s_per_100 > _SLOW_PACE_THRESHOLD_S:
            span = _SLOW_PACE_SATURATES_AT_S - _SLOW_PACE_THRESHOLD_S
            contributions["slow_pace"] = _WEIGHT_SLOW_PACE * _clamp(
                (pace_s_per_100 - _SLOW_PACE_THRESHOLD_S) / span
            )

    score = _clamp(sum(contributions.values()))

    return {
        "score": round(score, 4),
        "contributions": {k: round(v, 4) for k, v in contributions.items()},
        "counts": {
            "quiz_incorrect_count": incorrect,
            "back_nav_count": back_nav,
            "show_answer_used": show_answer,
            "time_on_section_s": round(seconds, 1),
            "pace_s_per_100_words": (
                round(pace_s_per_100, 1) if pace_s_per_100 is not None else None
            ),
            # Recorded so the stored breakdown can be recomputed: the wrong-answer weight
            # depends on it.
            "incorrect_saturates_at": incorrect_cap,
        },
    }


def detect(
    signals: Any, *, section_words: int | None = None, section_quizzes: int | None = None
) -> dict[str, Any] | None:
    """A reading in the shape `affect_detection` expects, or None when there is nothing to say.

    Returns None below `MIN_ACTIONABLE_SCORE` rather than a low-confidence `confused`. The gate
    would reject a low score anyway, but emitting one would put a stream of near-zero confusion
    readings into the research record and into the learner profile's affect history -- where they
    would dilute the sustain check that the OTHER channels depend on.
    """
    result = struggle_score(signals, section_words=section_words, section_quizzes=section_quizzes)
    if result["score"] < MIN_ACTIONABLE_SCORE:
        return None

    return {
        "affect_state": PERFORMANCE_STATE,
        # The score IS the confidence, and the naming is deliberate: it is a weighted count of
        # observed behaviours, not a calibrated probability, and it should not be compared
        # against a model's confidence as though the two meant the same thing.
        "affect_confidence": result["score"],
        "affect_source": AFFECT_SOURCE_PERFORMANCE,
        "performance_breakdown": result["contributions"],
        "performance_counts": result["counts"],
        "heuristic": True,
    }
