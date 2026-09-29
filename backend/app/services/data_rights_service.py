"""Erasure and data export — the code behind the promises in the participant-facing copy.

WHY THIS EXISTS

The consent form and the privacy policy both commit to deleting a participant's data on request,
within 24 hours. Until now nothing implemented that: the commitment was honoured by hand, which
is workable for one researcher and is not a control. A promise with no mechanism is a promise you
will keep until the week you are busy.

THE PART THE DATABASE DOES NOT DO FOR YOU

Deleting a `users` row cascades to twelve tables, which is most of a learner's footprint. It does
NOT cascade to `research_events`, because that table deliberately has no foreign keys: it is an
append-only research record keyed by an opaque `learner_id` STRING so that it survives the content
and accounts it refers to. That design is right, and it means erasure must delete those rows
explicitly. Relying on the cascade alone would leave every affect reading, self-report and
adaptation for that participant in the database while reporting success — the worst possible
outcome, since it looks like compliance.

`courses.created_by` is ON DELETE SET NULL rather than CASCADE, so a departing designer's courses
survive as system content instead of being destroyed along with their account.

WHAT ERASURE DOES NOT TOUCH

Aggregates already computed and published elsewhere, and rows that never carried an identifier.
Nothing here can reach a figure in a thesis chapter, and the export/erasure copy does not pretend
otherwise.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import AssessmentAttempt
from app.models.assistance_event import AssistanceEvent
from app.models.enrollment import Enrollment
from app.models.questionnaire_response import QuestionnaireResponse
from app.models.quiz_attempt import QuizAttempt
from app.models.raw_interaction_window import RawInteractionWindow
from app.models.research_event import ResearchEvent
from app.models.section_progress import SectionProgress
from app.models.section_visit import SectionVisit
from app.models.survey_response import SurveyResponse
from app.models.user import User

logger = structlog.get_logger(__name__)


async def erase_learner(db: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    """Delete a learner and everything recorded about them. Returns per-table counts.

    Commits. Raises on failure rather than reporting a partial erasure as a success: a caller
    that told a participant their data was gone when it was not would be worse than an error.
    """
    counts: dict[str, int] = {}

    # `research_events` FIRST and explicitly. It has no foreign key to `users` (by design — see
    # the module docstring), so nothing else will remove it, and doing it before the cascade means
    # a failure here aborts the whole erasure rather than leaving orphaned research rows behind.
    result = await db.execute(
        delete(ResearchEvent).where(ResearchEvent.learner_id == str(user_id))
    )
    counts["research_events"] = result.rowcount or 0

    # The raw interaction record, explicitly too: it is the most detailed thing held about a
    # learner, so its removal must not depend on the database enforcing the cascade.
    result = await db.execute(
        delete(RawInteractionWindow).where(RawInteractionWindow.learner_id == user_id)
    )
    counts["raw_interaction_windows"] = result.rowcount or 0

    # Everything below cascades from the user row. They are counted before deletion so the
    # receipt can say what was removed; the cascade then does the removal.
    for label, model, column in (
        ("assistance_events", AssistanceEvent, AssistanceEvent.learner_id),
        ("quiz_attempts", QuizAttempt, QuizAttempt.user_id),
        ("section_visits", SectionVisit, SectionVisit.user_id),
        ("section_progress", SectionProgress, SectionProgress.user_id),
        ("assessment_attempts", AssessmentAttempt, AssessmentAttempt.user_id),
        ("enrollments", Enrollment, Enrollment.user_id),
        ("questionnaire_responses", QuestionnaireResponse, QuestionnaireResponse.user_id),
        ("survey_responses", SurveyResponse, SurveyResponse.user_id),
    ):
        counts[label] = int(
            (await db.execute(select(func.count(model.id)).where(column == user_id))).scalar_one()
            or 0
        )

    user = await db.get(User, user_id)
    if user is None:
        await db.rollback()
        raise ValueError("user not found")

    await db.delete(user)
    await db.commit()

    counts["redis_keys"] = await forget_in_redis(user_id)
    logger.info("learner_erased", user_id=str(user_id), **counts)
    return counts


#: Marks a learner as erased for the research worker. Kept long enough to outlast anything still
#: queued in the stream (it drains every second; a Redis outage is the long case).
ERASED_KEY = "research:erased:{user_id}"
_ERASED_TTL_S = 7 * 24 * 3600


async def forget_in_redis(user_id: uuid.UUID | str) -> int:
    """Remove what Redis holds about a learner, and stop queued events reaching Postgres.

    The Postgres cascade does not reach Redis, which kept the learner's affect profile
    (`profile:learner:*`, no TTL), their session and screen state, and their per-section activity
    counters after erasure. And events still waiting in the research stream would have been
    written to `research_events` by the worker AFTER the erasure deleted the learner's rows -- the
    erased learner reappearing in the dataset. The `ERASED_KEY` marker is what the worker checks
    to drop them (`research_worker.drain_once`). Best-effort: returns the number of keys removed.
    """
    from app.services import redis_service

    uid = str(user_id)
    removed = await redis_service.delete_keys(
        f"profile:learner:{uid}", f"session:learner:{uid}", f"ui:learner:{uid}",
    )
    removed += await redis_service.delete_matching(f"activity:{uid}:*")
    await redis_service.set_str(ERASED_KEY.format(user_id=uid), "1", _ERASED_TTL_S)
    return removed


async def export_learner(db: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    """Everything held about one learner, as plain JSON-able data.

    Backs "you can ask what has been recorded about you and receive a copy". Deliberately
    exhaustive rather than curated: a subject-access response that quietly omits the interaction
    telemetry would answer a different question from the one being asked.
    """
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("user not found")

    async def rows(model, column) -> list[dict[str, Any]]:
        found = (await db.execute(select(model).where(column == user_id))).scalars().all()
        return [_as_dict(row) for row in found]

    research = (
        await db.execute(
            select(ResearchEvent)
            .where(ResearchEvent.learner_id == str(user_id))
            .order_by(ResearchEvent.timestamp.asc())
        )
    ).scalars().all()

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": {
            "id": str(user.id),
            "email_address": user.email_address,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "age_range": user.age_range,
            "degree_program": user.degree_program,
            "role": user.role.value,
            "consent_given_at": _iso(user.consent_given_at),
            "consent_version": user.consent_version,
            "consent_scopes": user.consent_scopes,
            "consent_withdrawn_at": _iso(user.consent_withdrawn_at),
            "webcam_enabled": user.webcam_enabled,
            "created_at": _iso(user.created_at),
        },
        "enrollments": await rows(Enrollment, Enrollment.user_id),
        "section_progress": await rows(SectionProgress, SectionProgress.user_id),
        "section_visits": await rows(SectionVisit, SectionVisit.user_id),
        "quiz_attempts": await rows(QuizAttempt, QuizAttempt.user_id),
        "assessment_attempts": await rows(AssessmentAttempt, AssessmentAttempt.user_id),
        "assistance_events": await rows(AssistanceEvent, AssistanceEvent.learner_id),
        "questionnaire_responses": await rows(
            QuestionnaireResponse, QuestionnaireResponse.user_id
        ),
        "survey_responses": await rows(SurveyResponse, SurveyResponse.user_id),
        "raw_interaction_windows": await rows(
            RawInteractionWindow, RawInteractionWindow.learner_id
        ),
        "research_events": [_as_dict(row) for row in research],
    }


async def purge_research_events_older_than(db: AsyncSession, *, days: int) -> int:
    """Delete research events past the retention limit. Returns the number removed.

    Backs the 90-day commitment in the participant-facing copy, which existed as a sentence and
    not as a job. Scoped to `research_events` on purpose: that is what the retention promise is
    about. A learner's own account and course progress are theirs to keep until they ask for
    erasure, and silently deleting someone's learning history after 90 days because a research
    limit expired would be a different and unwelcome product decision.
    """
    cutoff_ms = int(
        (datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000
    )
    result = await db.execute(
        delete(ResearchEvent).where(ResearchEvent.timestamp < cutoff_ms)
    )
    await db.commit()
    removed = result.rowcount or 0
    if removed:
        logger.info("research_events_purged", removed=removed, days=days)
    return removed


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _as_dict(row: Any) -> dict[str, Any]:
    """A model row as JSON-able primitives. UUIDs and datetimes become strings."""
    out: dict[str, Any] = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, uuid.UUID):
            out[column.name] = str(value)
        elif hasattr(value, "isoformat"):
            out[column.name] = value.isoformat()
        else:
            out[column.name] = value
    return out
