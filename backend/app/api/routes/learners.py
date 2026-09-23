"""Learner-scoped reads.

This module was an empty `APIRouter()` — three lines, mounted at `/api/v1/learners`, exposing
nothing. It now serves the learner's own help history, which is the read
`assistance_service.for_learner` was written for ("The read behind a learner-facing hint history")
and which had no route.

WHAT IS DELIBERATELY NOT RETURNED

No affect state, no confidence, no gate reason. `architecture.md` lists "showing detected affect
state to learners" as an anti-pattern — that data belongs on the designer analytics dashboard, and
telling a learner the system decided they looked confused changes the behaviour the system is
trying to measure. What comes back is what the learner already saw on screen: the help itself,
where it appeared, and what they did with it.
"""

import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.models.course import Lesson, Module, Section
from app.models.enrollment import Enrollment
from app.models.section_progress import SectionProgress
from app.models.user import Role, User
from app.schemas.base import CamelModel
from app.services import (
    assistance_service,
    content_context_service,
    course_ownership,
    learner_activity,
    video_resource_agent,
)
from app.services.research_logger import content_coords
from app.services.research_logger import emit as emit_research_event

router = APIRouter()


class AssistanceHistoryItem(CamelModel):
    """One piece of help the learner was shown."""

    id: uuid.UUID
    created_at: datetime
    #: `show_hint`, `show_alternative`, `suggest_break`, …
    action_type: str | None = None
    #: The text as it appeared on screen.
    hint_text: str | None = None
    section_id: uuid.UUID | None = None
    course_id: uuid.UUID | None = None
    #: What the learner did with it: `accepted`, `dismissed`, … or None if they did nothing.
    interaction: str | None = None
    #: Whether the next attempt after this help was correct. None when there was no next attempt,
    #: which is not the same as "no" and must not be collapsed into it.
    outcome_is_correct: bool | None = None


@router.get("/me/assistance", response_model=list[AssistanceHistoryItem])
async def my_assistance_history(
    limit: int = Query(default=50, ge=1, le=200),
    course_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    """The help this learner has been shown, newest first.

    Scoped to the caller by construction — there is no path parameter to point at somebody else.
    """
    events = await assistance_service.for_learner(
        db, learner_id=current_user.id, limit=limit, course_id=course_id
    )
    return [
        AssistanceHistoryItem(
            id=event.id,
            created_at=event.created_at,
            action_type=event.action_type,
            hint_text=event.hint_text,
            section_id=event.section_id,
            course_id=event.course_id,
            interaction=event.interaction,
            outcome_is_correct=event.outcome_is_correct,
        )
        for event in events
    ]


class RosterEntry(CamelModel):
    """One enrolled learner, as their course's designer sees them."""

    user_id: uuid.UUID
    first_name: str
    last_name: str
    email_address: str
    enrolled_at: datetime
    last_accessed_at: datetime | None = None
    status: str
    completed_sections: int
    total_sections: int


@router.get("/courses/{course_id}/roster", response_model=list[RosterEntry])
async def course_roster(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    """Who is enrolled on this course, and how far they have got.

    A designer had no way to see this at all. The only aggregate that existed
    (`/learner-profiles/{id}/progress`) spans every course a learner is enrolled in, so widening
    it would have handed one designer a learner's progress through other people's courses — this
    is course-scoped by construction instead, which is what a roster should be.

    Ownership-guarded on the same rule as the analytics screens it sits beside: your own courses,
    plus seeded/system content, which is shared and is what the pilot runs on.
    """
    await course_ownership.assert_can_view_course_analytics(db, current_user, course_id)

    total_sections = (
        await db.execute(
            select(func.count(Section.id))
            .join(Lesson, Section.lesson_id == Lesson.id)
            .join(Module, Lesson.module_id == Module.id)
            .where(Module.course_id == course_id)
        )
    ).scalar_one()

    # Completed sections per learner, restricted to sections of THIS course — a learner enrolled
    # on several courses must not have the others counted into this figure.
    completed_subq = (
        select(
            SectionProgress.user_id.label("user_id"),
            func.count(SectionProgress.id).label("completed"),
        )
        .join(Section, SectionProgress.section_id == Section.id)
        .join(Lesson, Section.lesson_id == Lesson.id)
        .join(Module, Lesson.module_id == Module.id)
        .where(Module.course_id == course_id)
        .group_by(SectionProgress.user_id)
        .subquery()
    )

    rows = (
        await db.execute(
            select(User, Enrollment, completed_subq.c.completed)
            .join(Enrollment, Enrollment.user_id == User.id)
            .outerjoin(completed_subq, completed_subq.c.user_id == User.id)
            .where(Enrollment.course_id == course_id)
            .order_by(Enrollment.enrolled_at.desc())
        )
    ).all()

    return [
        RosterEntry(
            user_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email_address=user.email_address,
            enrolled_at=enrollment.enrolled_at,
            last_accessed_at=enrollment.last_accessed_at,
            status=enrollment.status,
            completed_sections=int(completed or 0),
            total_sections=int(total_sections or 0),
        )
        for user, enrollment, completed in rows
    ]


# ── video help ("Watch a video explanation") ─────────────────────────────────────────
#
# On demand from a confusion card, outside the 30-second affect loop, so it can neither add latency
# to detection nor move a gate statistic. Returns only what the learner will see: a video (or a
# search link) and the agent's one-line reason. No affect state, per the module docstring.

#: One lookup per learner per window. Each uncached lookup spends 100 of 10,000 daily quota units.
_VIDEO_HELP_MIN_GAP_S = 5.0
_last_video_help: dict[str, float] = {}


class VideoHelpRequest(CamelModel):
    section_id: uuid.UUID
    #: The card the learner asked from, so "watched a video after THAT hint" is joinable.
    adaptation_id: str | None = None
    #: The hint text already on screen, so the agent looks for something that is not a repeat.
    hint_text: str | None = None
    session_id: str | None = None
    #: The Pedagogical agent's delegation brief, sent back by a `show_video` card whose video was
    #: still pending when the card was delivered. With it the sub-agent skips its own query step.
    concept: str | None = None
    query: str | None = None


class VideoHelpResponse(CamelModel):
    #: `embed` -- play `video_id` in the card. `link` -- open `url` (a YouTube search) in a new tab.
    kind: str
    url: str
    video_id: str | None = None
    title: str | None = None
    channel: str | None = None
    duration_s: int | None = None
    reason: str | None = None
    throttled: bool = False


class VideoHelpClosed(CamelModel):
    section_id: uuid.UUID
    video_id: str | None = None
    seconds_open: float = 0.0
    session_id: str | None = None


def _video_event(event_type: str, user: User, session_id: str | None, coords: dict,
                 payload: dict) -> dict:
    return {
        "event_type": event_type,
        "learner_id": str(user.id),
        "session_id": session_id,
        "cycle_number": 0,
        "timestamp": int(time.time() * 1000),
        **coords,
        "payload": payload,
    }


@router.post("/me/video-help", response_model=VideoHelpResponse)
async def video_help(
    body: VideoHelpRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    """Let the Video Resource Agent find one explanation video for this section."""
    user_key = str(current_user.id)
    now = time.monotonic()
    context = await learner_activity.attach(
        await content_context_service.build(str(body.section_id), db), user_key
    )
    if now - _last_video_help.get(user_key, -1e9) < _VIDEO_HELP_MIN_GAP_S:
        query, _concept = video_resource_agent.fallback_query(context)
        return VideoHelpResponse(
            kind="link", url=video_resource_agent.search_link(query), throttled=True
        )
    _last_video_help[user_key] = now

    coords = content_coords(context)
    await emit_research_event(_video_event(
        "video_help_requested", current_user, body.session_id, coords,
        {"from_adaptation_id": body.adaptation_id, "briefed": bool(body.concept)},
    ))

    brief = {"concept": body.concept, "query": body.query} if body.concept else None
    result = await video_resource_agent.find_video(context, body.hint_text, brief=brief)

    await emit_research_event(_video_event(
        "video_help_served", current_user, body.session_id, coords,
        {
            "from_adaptation_id": body.adaptation_id,
            "kind": result.get("kind"),
            "video_id": result.get("video_id"),
            "title": result.get("title"),
            "channel": result.get("channel"),
            "query": result.get("query"),
            "concept": result.get("concept"),
            "reason": result.get("reason"),
            "source": result.get("source"),
        },
    ))
    return VideoHelpResponse(**{k: result.get(k) for k in VideoHelpResponse.model_fields
                                if k in result})


@router.post("/me/video-help/closed", status_code=204)
async def video_help_closed(
    body: VideoHelpClosed,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    """Record how long the video stayed open. The only measure of whether it was watched."""
    context = await content_context_service.build(str(body.section_id), db)
    await emit_research_event(_video_event(
        "video_help_closed", current_user, body.session_id, content_coords(context),
        {"video_id": body.video_id, "seconds_open": round(max(0.0, body.seconds_open), 1)},
    ))
