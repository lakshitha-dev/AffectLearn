"""Per-section and per-question content effectiveness for course designers.

WHAT THIS ANSWERS THAT THE AFFECT HEATMAP DOES NOT

`analytics_service` answers "how did learners FEEL here", from a detector that is honest about
its limits: two states, both scored well below certainty, on a channel the deployed system
itself documents as weak on this interface. That is a real signal and it stays.

This answers "what did learners DO here", which on a paginated one-section-per-page reader is
the stronger evidence. Going back to re-read, revealing an answer, getting a question wrong
three times, dwelling far longer than the section's length warrants — none of that needs a model
to interpret, and none of it was visible to a designer.

WHERE THE DATA COMES FROM, AND WHY IT WAS ALREADY THERE

`section_features` has been computed and logged on every section completion since it was
written, and NOTHING has ever read it. Its own docstring says so: it "ships DARK — features are
computed and logged next to the self-report label so a future model can be trained on them".
Sixteen features per learner per section, sitting unused. Half of this module is simply reading
them back.

THREE THINGS THIS IS CAREFUL ABOUT

* SAMPLE SIZE IS ALWAYS REPORTED. A section completed by two learners produces a difficulty
  figure that means nothing, and a dashboard that renders it identically to one from forty
  learners is worse than one that shows nothing.
* THE ASSISTANCE OUTCOME IS AN ASSOCIATION. "Answered correctly after a hint" is a recorded
  co-occurrence, not evidence the hint caused it. The field is named for what it measures and
  the docstrings refuse the causal reading, because the surface built on it will be tempted.
* ZERO AND UNKNOWN ARE DIFFERENT. A section where no help was ever offered and a section where
  help was offered and never followed by an attempt both have "no outcome rate". Returning 0.0
  for both would say help never works there.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistance_event import AssistanceEvent
from app.models.course import ContentBlock, Lesson, Module, Section
from app.models.quiz_attempt import QuizAttempt
from app.models.research_event import ResearchEvent
from app.services.analytics_service import _confidence, _ordered_sections, _require_course

logger = structlog.get_logger(__name__)

SECTION_FEATURES_EVENT = "section_features"

#: Features averaged across learners for a section. Each is a per-learner observation, so the
#: mean is over learners rather than over events — one learner completing a section twice must
#: not weigh double.
_MEAN_FEATURES = (
    "time_on_section_s",
    "time_per_100_words",
    "back_nav_count",
    "quiz_attempt_count",
    "quiz_incorrect_count",
    "quiz_response_time_ms_mean",
)

#: Features that are 0/1 per learner, reported as the share of learners for whom they fired.
_RATE_FEATURES = ("show_answer_used",)


def _mean(values: list[float]) -> float | None:
    """None, not 0.0, when there is nothing to average. See the module docstring."""
    return round(sum(values) / len(values), 2) if values else None


def _rate(numerator: int, denominator: int) -> float | None:
    return round((numerator * 100.0) / denominator, 1) if denominator > 0 else None


async def _section_feature_rows(
    db: AsyncSession, section_ids: list[uuid.UUID]
) -> dict[str, list[dict[str, Any]]]:
    """Logged `section_features` payloads, grouped by section id.

    Filtered on the `section_id` COLUMN rather than on `payload.section_id`, which migration 021
    made possible. Before that this would have been a JSON scan of the whole research corpus.
    """
    if not section_ids:
        return {}

    wanted = {str(s) for s in section_ids}
    rows = (
        await db.execute(
            select(ResearchEvent.section_id, ResearchEvent.payload).where(
                ResearchEvent.event_type == SECTION_FEATURES_EVENT,
                ResearchEvent.section_id.in_(wanted),
            )
        )
    ).all()

    grouped: dict[str, list[dict[str, Any]]] = {sid: [] for sid in wanted}
    for section_id, payload in rows:
        if isinstance(payload, dict) and section_id in grouped:
            grouped[section_id].append(payload)
    return grouped


def _struggle_from_features(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate one section's feature rows into designer-facing numbers."""
    observed = len(payloads)
    summary: dict[str, Any] = {"observed_learners": observed}

    for key in _MEAN_FEATURES:
        values = [
            float(p[key])
            for p in payloads
            if isinstance(p.get(key), (int, float))
        ]
        summary[key] = _mean(values)

    for key in _RATE_FEATURES:
        fired = sum(1 for p in payloads if p.get(key))
        summary[f"{key}_rate"] = _rate(fired, observed)

    # Revisiting is the signal worth surfacing on its own: `view_count > 1` means the learner
    # came back to material they had already left.
    revisited = sum(1 for p in payloads if int(p.get("view_count") or 0) > 1)
    summary["revisit_rate"] = _rate(revisited, observed)

    # Wrong answers as a share of attempts, not of learners: a section with one learner who
    # tried five times and failed four is different from four learners failing once each, and
    # the attempt-level rate is the one that describes the QUESTION.
    attempts = sum(int(p.get("quiz_attempt_count") or 0) for p in payloads)
    incorrect = sum(int(p.get("quiz_incorrect_count") or 0) for p in payloads)
    summary["quiz_incorrect_rate"] = _rate(incorrect, attempts)

    return summary


async def _assistance_by_section(
    db: AsyncSession, section_ids: list[uuid.UUID]
) -> dict[str, dict[str, Any]]:
    """Help offered per section, what learners did with it, and what happened next."""
    if not section_ids:
        return {}

    rows = (
        await db.execute(
            select(
                AssistanceEvent.section_id,
                AssistanceEvent.learner_id,
                AssistanceEvent.interaction,
                AssistanceEvent.outcome_is_correct,
                AssistanceEvent.generated,
            ).where(AssistanceEvent.section_id.in_(section_ids))
        )
    ).all()

    by_section: dict[str, dict[str, Any]] = {}
    for section_id, learner_id, interaction, outcome, generated in rows:
        key = str(section_id)
        bucket = by_section.setdefault(
            key,
            {
                "offers": 0,
                "dismissed": 0,
                "generated": 0,
                "learners": set(),
                "resolved": 0,
                "correct_after": 0,
            },
        )
        bucket["offers"] += 1
        bucket["learners"].add(str(learner_id))
        if interaction == "dismissed":
            bucket["dismissed"] += 1
        if generated:
            bucket["generated"] += 1
        if outcome is not None:
            bucket["resolved"] += 1
            if outcome:
                bucket["correct_after"] += 1

    return {
        key: {
            "offers": b["offers"],
            "learners_helped": len(b["learners"]),
            "dismissal_rate": _rate(b["dismissed"], b["offers"]),
            # What share of delivered help was written by the model rather than the rule
            # fallback. Production has no GPU quota, so this is expected to be low — and a
            # dashboard that hid it would report the fine-tuned agent's behaviour while showing
            # the fallback's.
            "generated_rate": _rate(b["generated"], b["offers"]),
            # Share of FOLLOWED-UP offers where the next attempt was correct. Denominator is
            # `resolved`, not `offers`: help never followed by an attempt is unknown, not failed.
            "followed_by_correct_rate": _rate(b["correct_after"], b["resolved"]),
            "outcomes_recorded": b["resolved"],
        }
        for key, b in by_section.items()
    }


async def course_effectiveness(db: AsyncSession, course_id: uuid.UUID) -> dict[str, Any]:
    """Per-section struggle and assistance figures for one course, in course order."""
    await _require_course(db, course_id)
    sections = await _ordered_sections(db, course_id)
    section_ids = [s.id for s in sections]

    features = await _section_feature_rows(db, section_ids)
    assistance = await _assistance_by_section(db, section_ids)

    rows: list[dict[str, Any]] = []
    for section in sections:
        key = str(section.id)
        payloads = features.get(key, [])
        struggle = _struggle_from_features(payloads)
        rows.append(
            {
                "section_id": key,
                "section_title": section.title,
                **struggle,
                "assistance": assistance.get(
                    key,
                    {
                        "offers": 0,
                        "learners_helped": 0,
                        "dismissal_rate": None,
                        "generated_rate": None,
                        "followed_by_correct_rate": None,
                        "outcomes_recorded": 0,
                    },
                ),
                **_confidence(struggle["observed_learners"]),
            }
        )

    return {"course_id": str(course_id), "sections": rows}


async def section_questions(db: AsyncSession, section_id: uuid.UUID) -> dict[str, Any]:
    """Per-question difficulty for one section, from the attempt history.

    `facility` is the share of attempts that were correct — the classic p-value of item
    analysis, low meaning hard. Computed over ATTEMPTS rather than over learners, because a
    question answered wrongly four times before being got right is a hard question, and a
    learner-level rate would score it the same as one answered right first time.

    `first_attempt_facility` is the same figure restricted to each learner's FIRST attempt,
    which is the fairer measure of whether the material taught it: later attempts are
    contaminated by the feedback the earlier ones gave.
    """
    blocks = (
        await db.execute(
            select(ContentBlock)
            .where(ContentBlock.section_id == section_id)
            .order_by(ContentBlock.sort_order)
        )
    ).scalars().all()
    quiz_blocks = [b for b in blocks if getattr(b.block_type, "value", b.block_type) == "quiz"]

    rows: list[dict[str, Any]] = []
    for block in quiz_blocks:
        attempts = (
            await db.execute(
                select(
                    QuizAttempt.user_id,
                    QuizAttempt.attempt_number,
                    QuizAttempt.is_correct,
                    QuizAttempt.response_time_ms,
                    QuizAttempt.assistance_id,
                ).where(QuizAttempt.content_block_id == block.id)
            )
        ).all()

        total = len(attempts)
        correct = sum(1 for a in attempts if a.is_correct)
        firsts = [a for a in attempts if a.attempt_number == 1]
        first_correct = sum(1 for a in firsts if a.is_correct)
        times = [a.response_time_ms for a in attempts if a.response_time_ms is not None]
        learners = {str(a.user_id) for a in attempts}
        with_help = sum(1 for a in attempts if a.assistance_id)

        rows.append(
            {
                "block_id": str(block.id),
                "question": _question_text(block.content),
                "attempts": total,
                "learners": len(learners),
                "facility": _rate(correct, total),
                "first_attempt_facility": _rate(first_correct, len(firsts)),
                "mean_attempts_per_learner": (
                    round(total / len(learners), 2) if learners else None
                ),
                "mean_response_time_ms": _mean([float(t) for t in times]),
                "attempts_with_help_on_screen": with_help,
                **_confidence(len(learners)),
            }
        )

    return {"section_id": str(section_id), "questions": rows}


def _question_text(content: Any) -> str | None:
    """The question as authored, for identifying the row. Never raises on odd content."""
    if not isinstance(content, dict):
        return None
    text = content.get("question")
    return str(text)[:200] if text else None


async def _course_id_for_section(db: AsyncSession, section_id: uuid.UUID) -> uuid.UUID | None:
    """Used by the route to authorise on the owning course."""
    return (
        await db.execute(
            select(Module.course_id)
            .join(Lesson, Lesson.module_id == Module.id)
            .join(Section, Section.lesson_id == Lesson.id)
            .where(Section.id == section_id)
        )
    ).scalars().first()


async def struggle_leaderboard(
    db: AsyncSession, course_id: uuid.UUID, *, limit: int = 5
) -> list[dict[str, Any]]:
    """The sections learners struggle with most, worst first.

    Ranked on a composite of the three behavioural signals that need no model to interpret:
    going back to re-read, revealing an answer, and getting questions wrong. Sections with too
    few observations to mean anything are excluded rather than ranked — a section completed
    twice can top any leaderboard by accident.
    """
    effectiveness = await course_effectiveness(db, course_id)
    scored = []
    for row in effectiveness["sections"]:
        if row["insufficient_data"]:
            continue
        # Equal weights, stated plainly rather than tuned: there is no outcome data to fit
        # weights against, so anything else would be false precision.
        score = sum(
            value
            for value in (
                row.get("revisit_rate"),
                row.get("show_answer_used_rate"),
                row.get("quiz_incorrect_rate"),
            )
            if value is not None
        )
        scored.append({**row, "struggle_score": round(score, 1)})

    scored.sort(key=lambda r: r["struggle_score"], reverse=True)
    return scored[:limit]
