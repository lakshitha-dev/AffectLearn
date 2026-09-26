"""Seed realistic demonstration data: a learner, a designer, their courses and a class.

WHY THIS EXISTS

A new account is empty, so neither portal can be shown working: the learner has no courses, no
progress and no help history, and every designer analytics figure reads "insufficient data"
because each one needs at least five learners. This creates the smallest world in which both
portals behave as they do in use:

  * Dr Anjali Jayasinghe, a course designer who owns three courses — Python for Data Analysis
    and Web Development Fundamentals (published) and Database Design with SQL (a draft) — with
    authored simpler / alternative / harder variants on the sections learners find hardest.
  * Nimali Perera, a learner who has finished the web course and is three-quarters of the way
    through the Python one: a pre-test, section-by-section progress, quiz attempts (some wrong
    first time), revisits, a learner profile, and the help she was given — including the groupby
    section she is currently stuck on.
  * Twelve classmates who cannot log in, whose progress, affect, quiz answers and behaviour give
    the designer's heatmap, effectiveness, struggle and question-analysis screens a real cohort.

KEEPING IT OUT OF THE RESEARCH

Every account and course is flagged `is_demo` (migration 029), and `services/demo_scope.py`
excludes demo learners from the research export, the monitor CSV, the study audit, the educator
review sample and the gate replay. Real learners are never shown a demo course. Seeded research
events also carry `payload.synthetic = true`, and are dated between two and forty-odd days ago:
outside the monitor's 24-hour window, inside the 90-day retention period.

USAGE (dry run by default — the seed runs in a transaction that is rolled back)

    python -m app.db.seed_demo                                   # preview against DATABASE_URL
    python -m app.db.seed_demo --confirm                         # write it
    python -m app.db.seed_demo --reset --confirm                 # remove every demo row
    python -m app.db.seed_demo --database-url postgresql://... --confirm

Passwords for the two log-in accounts come from DEMO_LEARNER_PASSWORD / DEMO_DESIGNER_PASSWORD or
--learner-password / --designer-password. They are never printed, and never stored in the repo.

Idempotent: if the demo designer already exists, nothing is written. Use --reset first to rebuild.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import secrets
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agents.edges import GATE_LEARNER_REQUEST, GATE_OK
from app.agents.state import (
    AFFECT_SOURCE_BEHAVIORAL,
    AFFECT_SOURCE_FACIAL_GEOMETRY,
    AFFECT_SOURCE_LEARNER_REQUEST,
)
from app.core.security import hash_password
from app.db.demo_content import python_data, sql_design, web_fundamentals
from app.db.demo_content.hints import SECTION_TAGS, hint_for
from app.db.demo_content.people import (
    CLASS,
    DESIGNER,
    LEARNER,
    LEARNER_QUESTIONNAIRE,
    Classmate,
)
from app.models.assessment import (
    Assessment,
    AssessmentAttempt,
    AssessmentOption,
    AssessmentQuestion,
    QuestionResponse,
)
from app.models.assistance_event import AssistanceEvent
from app.models.content_version import ContentVersion
from app.models.course import ContentBlock, Course, Lesson, Module, Section
from app.models.email_token import EmailToken
from app.models.enrollment import Enrollment
from app.models.learner_profile import LearnerProfile
from app.models.questionnaire_response import QuestionnaireResponse
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_response import QuizBlockResponse
from app.models.research_event import ResearchEvent
from app.models.section_progress import SectionProgress
from app.models.section_visit import SectionVisit
from app.models.study_group import StudyGroup
from app.models.survey_response import SurveyResponse
from app.models.user import Role, User
from app.services import content_version_service, section_features

PHASE = "phase_b"
LEVELS = ("low", "intermediate", "advanced")

# A new study session starts after this long without activity.
_SESSION_GAP = timedelta(hours=3)

#: Salt for the class's random draws. The draws are deterministic, so this picks ONE class; it
#: was chosen so the analytics tell the course's actual story (groupby and Flexbox are the
#: confusion hotspots, the HTML opener the boredom spot), which `tests/db/test_seed_demo.py`
#: pins. Change the probabilities below and a new salt may be needed.
STORY_SALT = "28"


# ── what happens to one learner in one section ──────────────────────────────


@dataclass
class Help:
    """One piece of help delivered in a section."""

    action: str
    affect: str | None
    source: str
    confidence: float | None
    interaction: str | None
    gate: str = GATE_OK
    #: How many quiz attempts the learner had made before this help arrived.
    after_attempt: int = 0
    generated: bool = True


@dataclass
class SectionPlan:
    """A learner's time in one section, before it is written as rows."""

    affect: list[str]
    seconds: int
    views: int = 1
    #: Outcome of each successive attempt at the section's quiz. Empty: never attempted.
    attempts: list[bool] = field(default_factory=list)
    show_answer: bool = False
    helps: list[Help] = field(default_factory=list)
    complete: bool = True
    #: A second visit this many days after the first, in a new session (else straight after).
    revisit_days_later: float | None = None


# Probabilities per (low, intermediate, advanced), by how the section tends to feel.
_CONFUSED_P = {"intro": (0.15, 0.05, 0.0), "normal": (0.35, 0.15, 0.05),
               "moderate": (0.6, 0.35, 0.15), "hard": (0.95, 0.8, 0.45)}
_BORED_P = {"intro": (0.05, 0.35, 0.85), "normal": (0.05, 0.1, 0.25),
            "moderate": (0.0, 0.05, 0.1), "hard": (0.0, 0.0, 0.05)}
_REVISIT_P = {"intro": (0.05, 0.0, 0.0), "normal": (0.1, 0.05, 0.0),
              "moderate": (0.4, 0.2, 0.05), "hard": (0.75, 0.5, 0.15)}
#: Whether any engaged reading is seen at all: a learner lost in a hard section, or bored by one
#: they already know, can go the whole section without one.
_ENGAGED_P = {"intro": (0.95, 0.9, 0.55), "normal": (0.95, 0.97, 0.9),
              "moderate": (0.8, 0.9, 0.97), "hard": (0.5, 0.7, 0.9)}
_SHOW_ANSWER_P = (0.65, 0.4, 0.12)
_FIRST_CORRECT = {"low": 0.5, "intermediate": 0.72, "advanced": 0.9}
_TAG_ADJUST = {"intro": 0.1, "normal": 0.0, "moderate": -0.1, "hard": -0.3}
_PACE = {"low": 1.45, "intermediate": 1.1, "advanced": 0.75}
_TAG_PACE = {"intro": 0.8, "normal": 1.0, "moderate": 1.15, "hard": 1.5}


def _interaction(rng: random.Random) -> str:
    return rng.choices(("accepted", "dismissed", "applied"), weights=(55, 30, 15))[0]


def simulate(rng: random.Random, *, level: str, tag: str, minutes: int, has_quiz: bool,
             has_exercise: bool, adaptive: bool) -> SectionPlan:
    """A plausible visit for a learner of this level to a section of this kind."""
    i = LEVELS.index(level)
    confused = rng.random() < _CONFUSED_P[tag][i]
    bored = rng.random() < _BORED_P[tag][i]

    seconds = minutes * 60 * _PACE[level] * _TAG_PACE[tag] * rng.uniform(0.85, 1.2)
    if tag == "intro" and level == "advanced":
        seconds *= 0.7

    affect = ["engaged"]
    if bored:
        affect += ["bored"] * rng.randint(1, 3)
    if confused:
        affect += ["confused"] * rng.randint(1, 3 if tag == "hard" else 2)
    affect += ["engaged"] * rng.randint(1, 2)
    if rng.random() > _ENGAGED_P[tag][i]:
        affect = [label for label in affect if label != "engaged"] or (
            ["confused"] if tag in ("moderate", "hard") else ["bored"]
        )

    helps: list[Help] = []
    if adaptive:
        if confused and (tag == "hard" or (tag == "moderate" and rng.random() < 0.5)):
            helps.append(Help("show_hint", "confused", AFFECT_SOURCE_BEHAVIORAL,
                              round(rng.uniform(0.72, 0.88), 2), _interaction(rng)))
            if level == "low" or (tag == "hard" and rng.random() < 0.5):
                helps.append(Help(rng.choice(("show_breakdown", "show_alternative")), "confused",
                                  AFFECT_SOURCE_BEHAVIORAL, round(rng.uniform(0.75, 0.9), 2),
                                  _interaction(rng)))
        elif bored and tag == "intro" and level == "advanced":
            helps.append(Help("increase_difficulty", "bored", AFFECT_SOURCE_FACIAL_GEOMETRY,
                              round(rng.uniform(0.78, 0.93), 2), _interaction(rng)))

    attempts: list[bool] = []
    if has_quiz:
        p = _FIRST_CORRECT[level] + _TAG_ADJUST[tag] + (0.12 if helps else 0.0)
        attempts.append(rng.random() < min(0.97, max(0.1, p)))
        if not attempts[-1]:
            attempts.append(rng.random() < 0.8)
            if not attempts[-1]:
                attempts.append(True)

    return SectionPlan(
        affect=affect,
        seconds=int(seconds),
        views=2 if rng.random() < _REVISIT_P[tag][i] else 1,
        attempts=attempts,
        show_answer=has_exercise and rng.random() < _SHOW_ANSWER_P[i],
        helps=helps,
    )


# ── Nimali's history, section by section ────────────────────────────────────

_B, _F, _R = AFFECT_SOURCE_BEHAVIORAL, AFFECT_SOURCE_FACIAL_GEOMETRY, AFFECT_SOURCE_LEARNER_REQUEST

#: (days ago, hour of day) each section was started, and what happened there.
NIMALI_WEB: list[tuple[float, float, SectionPlan]] = [
    (27, 19.5, SectionPlan(["engaged", "engaged", "bored", "bored", "engaged"], 250, attempts=[True],
                           helps=[Help("increase_difficulty", "bored", _F, 0.86, "accepted")])),
    (27, 19.7, SectionPlan(["engaged", "engaged", "engaged"], 380, attempts=[True])),
    (25, 20.2, SectionPlan(["engaged", "confused", "engaged", "engaged"], 560, attempts=[False, True],
                           helps=[Help("show_hint", "confused", _B, 0.76, "accepted",
                                       after_attempt=1)])),
    (23, 18.8, SectionPlan(["engaged", "confused", "confused", "confused", "engaged", "engaged"], 980,
                           views=2, attempts=[True],
                           helps=[Help("show_hint", "confused", _B, 0.81, "dismissed"),
                                  Help("show_breakdown", "confused", _B, 0.84, "applied")])),
    (21, 20.0, SectionPlan(["engaged", "engaged", "engaged"], 520, attempts=[True])),
    (21, 20.2, SectionPlan(["engaged", "engaged", "bored", "engaged"], 470)),
]

NIMALI_PYTHON: list[tuple[float, float, SectionPlan]] = [
    (16, 20.3, SectionPlan(["engaged", "engaged"], 330, attempts=[True])),
    (14, 19.0, SectionPlan(["engaged", "engaged", "confused", "engaged"], 510, attempts=[True])),
    (14, 19.2, SectionPlan(["engaged", "engaged", "engaged"], 560)),
    (11, 21.0, SectionPlan(["engaged", "confused", "engaged"], 470, attempts=[False, True],
                           helps=[Help("show_hint", "confused", _B, 0.77, "accepted")])),
    (9, 19.4, SectionPlan(["engaged", "engaged", "bored", "engaged"], 450, attempts=[True])),
    (6, 20.1, SectionPlan(["engaged", "confused", "engaged", "engaged"], 720, attempts=[True],
                          helps=[Help("show_hint", "confused", _R, None, "accepted",
                                      gate=GATE_LEARNER_REQUEST)])),
    # groupby: where she is now. Two visits, help offered twice, not yet completed.
    (4, 19.6, SectionPlan(["engaged", "confused", "confused", "confused", "engaged"], 1260,
                          views=2, revisit_days_later=2, attempts=[False], complete=False,
                          helps=[Help("show_hint", "confused", _B, 0.79, "dismissed"),
                                 Help("show_breakdown", "confused", _B, 0.83, "accepted",
                                      after_attempt=1)])),
]

#: Nimali's pre-test: three of four, wrong on the "no return statement" item.
NIMALI_PRETEST = [True, True, False, True]


# ── the writer ──────────────────────────────────────────────────────────────


def _ms(when: datetime) -> int:
    return int(when.timestamp() * 1000)


def _sections(course: Course) -> list[Section]:
    return [s for m in course.modules for le in m.lessons for s in le.sections]


def _originals(section: Section) -> list[ContentBlock]:
    return sorted((b for b in section.content_blocks if b.variant_key == "original"),
                  key=lambda b: b.sort_order)


def _kind(block: ContentBlock) -> str:
    return getattr(block.block_type, "value", block.block_type)


class _Writer:
    """Adds rows for the seeded world and counts them for the report."""

    def __init__(self, db: AsyncSession, now: datetime):
        self.db = db
        self.now = now
        self.counts: Counter = Counter()
        # learner id -> [session id, last activity, next sequence number, next cycle]
        self._sessions: dict[uuid.UUID, list[Any]] = {}
        self.session_totals: Counter = Counter()
        # Help -> the attempt that followed it, linked by `settle` once both rows exist.
        self._outcomes: list[tuple[AssistanceEvent, QuizAttempt]] = []
        self._linked: set[str] = set()

    def add(self, obj: Any) -> Any:
        self.db.add(obj)
        self.counts[obj.__tablename__] += 1
        return obj

    async def settle(self) -> None:
        """Write what is pending, then point each help event at the attempt that followed it.

        The ORM orders inserts only along relationships, and most foreign keys here have none,
        so a row can reach the database before the row it points at. Postgres rejects that
        (SQLite, which the tests use, does not check unless asked). Parents are flushed before
        their children throughout; this handles the one link made inside a batch.
        """
        await self.db.flush()
        for event, attempt in self._outcomes:
            event.outcome_attempt_id = attempt.id
            event.outcome_is_correct = attempt.is_correct
            event.outcome_resolved_at = attempt.submitted_at
        self._outcomes.clear()
        await self.db.flush()

    def ago(self, days: float, hour: float | None = None) -> datetime:
        when = self.now - timedelta(days=days)
        if hour is not None:
            when = when.replace(hour=int(hour), minute=int((hour % 1) * 60), second=0,
                                microsecond=0)
        return when

    # sessions and research events

    def _session(self, learner: User, when: datetime) -> list[Any]:
        state = self._sessions.get(learner.id)
        if state is None or when - state[1] > _SESSION_GAP:
            self.session_totals[learner.id] += 1
            sid = f"demo-{learner.id.hex[:8]}-{self.session_totals[learner.id]:02d}"
            state = [sid, when, 1, 1]
            self._sessions[learner.id] = state
        state[1] = when
        return state

    def event(self, learner: User, group: str, when: datetime, event_type: str,
              payload: dict[str, Any], *, course: Course, section: Section,
              new_cycle: bool = True) -> int:
        state = self._session(learner, when)
        if new_cycle:
            state[3] += 1
        self.add(ResearchEvent(
            event_type=event_type,
            learner_id=str(learner.id),
            session_id=state[0],
            cycle_number=state[3],
            timestamp=_ms(when),
            sequence_number=state[2],
            payload={**payload, "synthetic": True, "demo": True},
            phase=PHASE,
            group=group,
            course_id=str(course.id),
            section_id=str(section.id),
        ))
        state[2] += 1
        return state[3]

    # one section

    def section(self, rng: random.Random, learner: User, group: str, enrollment: Enrollment,
                course: Course, section: Section, plan: SectionPlan, start: datetime,
                version_id: uuid.UUID | None) -> datetime:
        """Write one learner's time in one section. Returns when they left it."""
        blocks = _originals(section)
        quiz = next((b for b in blocks if _kind(b) == "quiz"), None)
        has_exercise = any(_kind(b) == "exercise" for b in blocks)

        # Visits: the first gets most of the time; a revisit comes straight after, or days later.
        first_share = 0.65 if plan.views > 1 else 1.0
        visits = [(start, int(plan.seconds * first_share), "next")]
        if plan.views > 1:
            if plan.revisit_days_later:
                again, source = start + timedelta(days=plan.revisit_days_later), "resume"
            else:
                again, source = start + timedelta(seconds=visits[0][1] + 150), "back"
            visits.append((again, plan.seconds - visits[0][1], source))
        for entered, seconds, source in visits:
            self.add(SectionVisit(
                user_id=learner.id, section_id=section.id, enrollment_id=enrollment.id,
                entered_at=entered, left_at=entered + timedelta(seconds=seconds),
                duration_seconds=seconds, entry_source=source,
            ))
        end = visits[-1][0] + timedelta(seconds=visits[-1][1])

        # When each thing happened. Readings are spread over the first visit, with the last
        # few in the revisit; the quiz comes late in the final visit; help arrives at the
        # reading that prompted it, or just after the attempt it followed.
        n = len(plan.affect)
        moments = [visits[0][0] + timedelta(seconds=visits[0][1] * (k + 1) / (n + 2))
                   for k in range(n)]
        if len(visits) > 1:
            tail = max(1, round(n / 2.5))
            for j, k in enumerate(range(n - tail, n)):
                moments[k] = visits[1][0] + timedelta(seconds=30 * (j + 1))
        quiz_at = visits[-1][0] + timedelta(seconds=visits[-1][1] * 0.85)
        attempt_times = [quiz_at + timedelta(seconds=50 * k) for k in range(len(plan.attempts))]

        timeline: list[tuple[datetime, int, str, Any]] = [
            (when, 0, "reading", label) for label, when in zip(plan.affect, moments)
        ]
        for i, h in enumerate(plan.helps):
            if h.after_attempt and attempt_times:
                when = attempt_times[min(h.after_attempt, len(attempt_times)) - 1]
                when += timedelta(seconds=20)
            else:
                k = next((k for k, lab in enumerate(plan.affect) if lab == h.affect), 0)
                when = moments[min(n - 1, k + i)] + timedelta(seconds=15)
            timeline.append((when, 1, "help", h))
        for k, (correct, when) in enumerate(zip(plan.attempts, attempt_times)):
            timeline.append((when, 2, "attempt", (k, correct)))
        timeline.sort(key=lambda item: (item[0], item[1]))

        # Written in time order, so sessions and sequence numbers follow the clock.
        options = (quiz.content.get("options") or []) if quiz is not None else []
        right = next((o["id"] for o in options if o.get("isCorrect")), None)
        wrong = [o["id"] for o in options if not o.get("isCorrect")]
        helps: list[tuple[Help, AssistanceEvent]] = []
        attempts: list[QuizAttempt] = []
        for when, _, kind, item in timeline:
            if kind == "reading":
                facial = item == "bored" or (item == "engaged" and rng.random() < 0.5)
                self.event(
                    learner, group, when,
                    "facial_affect_detected" if facial else "behavioral_affect_detected",
                    {"affect_state": item, "confidence": round(rng.uniform(0.62, 0.91), 3),
                     "model_kind": "geometry" if facial else "behavioral_gbdt"},
                    course=course, section=section,
                )
            elif kind == "help":
                helps.append((item, self._help(rng, learner, group, course, section, item, when)))
            elif quiz is not None:
                k, correct = item
                choice = right if correct else rng.choices(
                    wrong, weights=[3] + [1] * (len(wrong) - 1))[0]
                # The help on screen when they answered: the latest one before this attempt
                # that they did not close.
                on_screen = next((e for h, e in reversed(helps)
                                  if h.after_attempt == k and h.interaction != "dismissed"), None)
                attempt = self.add(QuizAttempt(
                    id=uuid.uuid4(), user_id=learner.id, content_block_id=quiz.id,
                    section_id=section.id, attempt_number=k + 1, selected_answers=[choice],
                    is_correct=correct, response_time_ms=rng.randint(8000, 35000),
                    assistance_id=on_screen.adaptation_id if on_screen else None,
                    submitted_at=when, created_at=when, updated_at=when,
                ))
                attempts.append(attempt)
                if on_screen is not None and on_screen.adaptation_id not in self._linked:
                    self._linked.add(on_screen.adaptation_id)
                    self._outcomes.append((on_screen, attempt))

        if attempts:
            # The per-block summary keeps the FIRST answer, as the real route does.
            self.add(QuizBlockResponse(
                user_id=learner.id, content_block_id=quiz.id,
                selected_answers=attempts[0].selected_answers, is_correct=attempts[0].is_correct,
                created_at=attempts[0].submitted_at, updated_at=attempts[0].submitted_at,
            ))

        if not plan.complete:
            return end

        self.add(SectionProgress(
            user_id=learner.id, section_id=section.id, enrollment_id=enrollment.id,
            completed_at=end, time_spent_seconds=plan.seconds, affect_states=list(plan.affect),
            content_version_id=version_id, created_at=end, updated_at=end,
        ))
        times = [a.response_time_ms for a in attempts]
        features = section_features.from_signals(
            {
                "time_on_section_s": plan.seconds,
                "view_count": plan.views,
                "back_nav_count": plan.views - 1,
                "show_answer_used": 1 if plan.show_answer else 0,
                "quiz_attempt_count": len(attempts),
                "quiz_incorrect_count": sum(1 for a in attempts if not a.is_correct),
                "quiz_response_time_ms_mean": sum(times) / len(times) if times else 0,
                "exercise_attempt_count": 1 if has_exercise else 0,
                "adaptation_delivered_count": len(plan.helps),
                "adaptation_dismissed_count": sum(
                    1 for h in plan.helps if h.interaction == "dismissed"),
            },
            str(section.id),
            section_features.section_shape_from_blocks(blocks),
        )
        self.event(learner, group, end, "section_features", features,
                   course=course, section=section, new_cycle=False)
        return end

    def _help(self, rng: random.Random, learner: User, group: str, course: Course,
              section: Section, h: Help, when: datetime) -> AssistanceEvent:
        adaptation_id = f"demo-{uuid.uuid4().hex[:24]}"
        cycle = self.event(
            learner, group, when, "adaptation_delivered",
            {"adaptation_id": adaptation_id, "action": h.action, "variant": h.action,
             "generated": h.generated, "fallback": not h.generated},
            course=course, section=section,
        )
        interacted = when + timedelta(seconds=rng.randint(12, 70)) if h.interaction else None
        return self.add(AssistanceEvent(
            adaptation_id=adaptation_id,
            learner_id=learner.id,
            session_id=self._sessions[learner.id][0],
            cycle_number=cycle,
            course_id=course.id,
            section_id=section.id,
            affect_state=h.affect,
            affect_source=h.source,
            affect_confidence=h.confidence,
            gate_reason=h.gate,
            action_type=h.action,
            urgency="high" if h.gate == GATE_LEARNER_REQUEST else "medium",
            rationale=_rationale(h, section.title),
            hint_text=hint_for(section.title, h.action),
            variant=h.action,
            generated=h.generated,
            fallback=not h.generated,
            fallback_reason=None if h.generated else "llm_timeout",
            delivered_at=when,
            delivery_failed=False,
            interaction=h.interaction,
            interacted_at=interacted,
            phase=PHASE,
            group=group,
            created_at=when,
            updated_at=interacted or when,
        ))


def _rationale(h: Help, title: str) -> str:
    if h.gate == GATE_LEARNER_REQUEST:
        return f"The learner asked for help on {title}; start with a hint grounded in the example."
    if h.action == "increase_difficulty":
        return f"Sustained disengagement on {title}, which covers material they already know."
    if h.action == "show_hint":
        return f"Sustained confusion on {title}; point at the step to re-read before explaining."
    return f"Confusion persisted on {title} after a hint; break the idea into smaller steps."


# ── seeding ─────────────────────────────────────────────────────────────────


def _user(email: str, first: str, last: str, *, password: str, role: Role, created: datetime,
          age: str | None = None, degree: str | None = None, consent: datetime | None = None,
          webcam: bool = False) -> User:
    return User(
        id=uuid.uuid4(),
        email_address=email,
        password_hash=hash_password(password),
        first_name=first,
        last_name=last,
        age_range=age,
        degree_program=degree,
        role=role,
        is_active=True,
        email_verified=True,
        consent_given_at=consent,
        webcam_enabled=webcam,
        is_demo=True,
        created_at=created,
        updated_at=created,
    )


async def _publish(w: _Writer, course: Course, designer: User, published: datetime) -> uuid.UUID:
    version = await content_version_service.snapshot_on_publish(
        w.db, course_id=course.id, published_by=designer.id
    )
    if version is None:
        raise RuntimeError(f"could not snapshot {course.title!r}")
    version.published_at = published
    w.counts[ContentVersion.__tablename__] += 1
    return version.id


def _pretest(w: _Writer, learner: User, enrollment: Enrollment, pre: Assessment,
             answers: list[bool], when: datetime) -> float:
    attempt = w.add(AssessmentAttempt(
        id=uuid.uuid4(), user_id=learner.id, assessment_id=pre.id, enrollment_id=enrollment.id,
        score=sum(answers), max_score=len(answers), attempt_number=1,
        started_at=when - timedelta(minutes=4), submitted_at=when, created_at=when,
        updated_at=when,
    ))
    for q, correct in zip(pre.questions, answers):
        chosen = next(o for o in q.options if o.is_correct == correct)
        w.add(QuestionResponse(attempt_id=attempt.id, question_id=q.id,
                               selected_option_id=chosen.id, is_correct=correct))
    return sum(answers) / len(answers)


def _skill(ratio: float) -> str:
    return "low" if ratio < 0.5 else "intermediate" if ratio < 0.8 else "advanced"


def _profile(affect: list[str], sessions: int, *, skill: str, mastery: dict[str, float],
             preferences: dict[str, str], updated: datetime) -> dict[str, Any]:
    history = affect[-20:]
    # A profile must not end mid-episode: the gate reads the tail of this history, and a stale
    # run of "confused" would let the first live reading look like sustained confusion.
    while history and history[-1] != "engaged":
        history.pop()
    return {
        "affect_state": "engaged",
        "affect_history": history,
        "skill_level": skill,
        "topic_mastery": mastery,
        "format_preferences": preferences,
        "session_count": sessions,
        "cycle_count": len(affect),
        "updated_at": _ms(updated),
    }


def _mastery(plan: SectionPlan) -> float:
    if not plan.attempts:
        return 0.8 if not plan.show_answer else 0.6
    return 0.9 if plan.attempts[0] else 0.65 if len(plan.attempts) == 2 else 0.5


async def seed_demo(db: AsyncSession, *, learner_password: str, designer_password: str,
                    now: datetime | None = None) -> dict[str, Any]:
    """Create the demo world. Flushes but does NOT commit — the caller decides.

    Returns `{"skipped": bool, "counts": {table: rows}}`.
    """
    existing = (await db.execute(
        select(User.id).where(User.email_address == DESIGNER["email_address"])
    )).scalar_one_or_none()
    if existing is not None:
        return {"skipped": True, "counts": {}}

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    w = _Writer(db, now)

    # The designer and her courses.
    designer = w.add(_user(DESIGNER["email_address"], DESIGNER["first_name"],
                           DESIGNER["last_name"], password=designer_password,
                           role=Role.course_designer, created=w.ago(95)))
    await db.flush()  # before the courses that point at her
    web, sql, python = web_fundamentals.build(), sql_design.build(), python_data.build()
    # Python is the newest published course, so her dashboard opens on it; the SQL draft was
    # started earlier and is still being written.
    for course, created, updated in ((web, 82, 30), (sql, 60, 3), (python, 52, 9)):
        course.created_by = designer.id
        course.is_demo = True
        course.created_at = w.ago(created)
        course.updated_at = w.ago(updated)
        w.add(course)
        for m in course.modules:
            w.counts["modules"] += 1
            for le in m.lessons:
                w.counts["lessons"] += 1
                for s in le.sections:
                    w.counts["sections"] += 1
                    w.counts["content_blocks"] += len(s.content_blocks)
    pre = python_data.build_pre()
    await db.flush()
    pre.module_id = python.modules[0].id
    w.add(pre)
    await db.flush()

    versions = {
        web.id: await _publish(w, web, designer, w.ago(78)),
        python.id: await _publish(w, python, designer, w.ago(50)),
    }

    # The demo learner.
    nimali = w.add(_user(LEARNER["email_address"], LEARNER["first_name"], LEARNER["last_name"],
                         password=learner_password, role=Role.learner, created=w.ago(28, 19),
                         age=LEARNER["age_range"], degree=LEARNER["degree_program"],
                         consent=w.ago(28, 19.1), webcam=True))
    await db.flush()  # before the rows that point at her
    w.add(QuestionnaireResponse(user_id=nimali.id, responses=LEARNER_QUESTIONNAIRE,
                                submitted_at=w.ago(28, 19.2)))
    w.add(StudyGroup(user_id=nimali.id, group="adaptive"))
    await db.flush()

    rng = random.Random("nimali")
    ratio = 0.0
    nimali_affect: list[str] = []
    mastery: dict[str, float] = {}
    last_seen = w.now
    for course, script, enrolled_days in ((web, NIMALI_WEB, 27), (python, NIMALI_PYTHON, 16)):
        enrollment = w.add(Enrollment(id=uuid.uuid4(), user_id=nimali.id, course_id=course.id,
                                      enrolled_at=w.ago(enrolled_days, 19.3), status="active"))
        await db.flush()
        if course is python:
            ratio = _pretest(w, nimali, enrollment, pre, NIMALI_PRETEST, w.ago(16, 20.1))
        completed = 0
        for section, (days, hour, plan) in zip(_sections(course), script):
            last_seen = w.section(rng, nimali, "adaptive", enrollment, course, section, plan,
                                  w.ago(days, hour), versions.get(course.id))
            nimali_affect += plan.affect
            if plan.complete:
                completed += 1
                mastery[str(section.id)] = _mastery(plan)
        enrollment.progress_percentage = completed * 100.0 / len(_sections(course))
        enrollment.last_accessed_at = last_seen
    await w.settle()
    w.add(LearnerProfile(user_id=nimali.id, profile=_profile(
        nimali_affect, w.session_totals[nimali.id], skill=_skill(ratio), mastery=mastery,
        preferences={"preferred_format": "interactive", "worked_examples": "high"},
        updated=last_seen,
    )))

    # The class.
    for mate in CLASS:
        await _classmate(w, mate, {"web": web, "python": python}, versions, pre)

    await w.settle()
    return {"skipped": False, "counts": dict(sorted(w.counts.items()))}


async def _classmate(w: _Writer, mate: Classmate, courses: dict[str, Course],
                     versions: dict[uuid.UUID, uuid.UUID], pre: Assessment) -> None:
    rng = random.Random(f"{mate.email}|{STORY_SALT}")
    first_start = {"web": rng.uniform(38, 58), "python": rng.uniform(18, 34)}
    learner = w.add(_user(
        mate.email, mate.first, mate.last, password=secrets.token_urlsafe(32), role=Role.learner,
        created=w.ago(first_start["web"] + 1), age=mate.age, degree=mate.degree,
        consent=w.ago(first_start["web"] + 1), webcam=rng.random() < 0.8,
    ))
    await w.db.flush()  # before the rows that point at them
    w.add(StudyGroup(user_id=learner.id, group=mate.group))
    await w.db.flush()

    affect: list[str] = []
    skill = mate.level
    latest = w.now - timedelta(days=2, hours=3)
    for key, share in (("web", mate.web), ("python", mate.python)):
        if share is None:
            continue
        course = courses[key]
        sections = _sections(course)
        done = round(share * len(sections))
        start = w.ago(first_start[key], rng.uniform(9, 21))
        enrollment = w.add(Enrollment(id=uuid.uuid4(), user_id=learner.id, course_id=course.id,
                                      enrolled_at=start - timedelta(minutes=10), status="active"))
        await w.db.flush()
        if key == "python":
            correct = {"low": rng.choice((1, 2)), "intermediate": rng.choice((2, 3)),
                       "advanced": rng.choice((3, 4, 4))}[mate.level]
            answers = [True] * correct + [False] * (len(pre.questions) - correct)
            rng.shuffle(answers)
            skill = _skill(_pretest(w, learner, enrollment, pre, answers,
                                    start - timedelta(minutes=5)))

        plans = []
        for section in sections[:done]:
            blocks = _originals(section)
            plans.append(simulate(
                rng, level=mate.level, tag=SECTION_TAGS.get(section.title, "normal"),
                minutes=section.estimated_duration_minutes or 8,
                has_quiz=any(_kind(b) == "quiz" for b in blocks),
                has_exercise=any(_kind(b) == "exercise" for b in blocks),
                adaptive=mate.group == "adaptive",
            ))
        # Two sections per sitting, a day or two apart — shifted back if it would run past
        # `latest`, so nothing lands inside the monitor's 24-hour window.
        starts, t = [], start
        for k, plan in enumerate(plans):
            if k and k % 2 == 0:
                t += timedelta(hours=rng.uniform(20, 60))
            starts.append(t)
            t += timedelta(seconds=plan.seconds * 1.1 + 240)
        if starts and t > latest:
            shift = t - latest
            starts = [s - shift for s in starts]
        last_seen = start
        for section, plan, when in zip(sections, plans, starts):
            last_seen = w.section(rng, learner, mate.group, enrollment, course, section, plan,
                                  when, versions.get(course.id))
            affect += plan.affect
        enrollment.progress_percentage = done * 100.0 / len(sections)
        enrollment.last_accessed_at = last_seen

    await w.settle()
    w.add(LearnerProfile(user_id=learner.id, profile=_profile(
        affect, w.session_totals[learner.id], skill=skill, mastery={}, preferences={},
        updated=w.now - timedelta(days=2),
    )))


# ── reset ───────────────────────────────────────────────────────────────────


async def reset_demo(db: AsyncSession) -> dict[str, int]:
    """Delete every demo account and demo course, and everything recorded against them.

    Explicit deletes in dependency order rather than relying on ON DELETE CASCADE, so the reset
    is the same on every database (SQLite does not enforce foreign keys by default). Flushes but
    does NOT commit.
    """
    counts: Counter = Counter()
    user_ids = list((await db.execute(select(User.id).where(User.is_demo.is_(True)))).scalars())
    course_ids = list((await db.execute(select(Course.id).where(Course.is_demo.is_(True)))).scalars())

    async def purge(model, *conditions) -> None:
        result = await db.execute(delete(model).where(*conditions))
        counts[model.__tablename__] += result.rowcount or 0

    if user_ids or course_ids:
        await purge(ResearchEvent, ResearchEvent.learner_id.in_([str(u) for u in user_ids])
                    | ResearchEvent.course_id.in_([str(c) for c in course_ids]))

    if user_ids:
        attempt_ids = select(AssessmentAttempt.id).where(AssessmentAttempt.user_id.in_(user_ids))
        await purge(QuestionResponse, QuestionResponse.attempt_id.in_(attempt_ids))
        await purge(AssessmentAttempt, AssessmentAttempt.user_id.in_(user_ids))
        await purge(AssistanceEvent, AssistanceEvent.learner_id.in_(user_ids))
        await purge(QuizAttempt, QuizAttempt.user_id.in_(user_ids))
        await purge(QuizBlockResponse, QuizBlockResponse.user_id.in_(user_ids))
        await purge(SectionVisit, SectionVisit.user_id.in_(user_ids))
        await purge(SectionProgress, SectionProgress.user_id.in_(user_ids))
        for model in (LearnerProfile, QuestionnaireResponse, StudyGroup, SurveyResponse,
                      EmailToken, Enrollment):
            await purge(model, model.user_id.in_(user_ids))

    for course in (await db.execute(select(Course).where(Course.id.in_(course_ids)))).scalars():
        # The course points at its current version and the version at the course; break the
        # cycle before either is deleted.
        course.published_version_id = None
        await db.flush()
        module_ids = select(Module.id).where(Module.course_id == course.id)
        assessment_ids = select(Assessment.id).where(Assessment.module_id.in_(module_ids))
        question_ids = select(AssessmentQuestion.id).where(
            AssessmentQuestion.assessment_id.in_(assessment_ids))
        await purge(AssessmentOption, AssessmentOption.question_id.in_(question_ids))
        await purge(AssessmentQuestion, AssessmentQuestion.id.in_(question_ids))
        await purge(Assessment, Assessment.id.in_(assessment_ids))
        await purge(ContentVersion, ContentVersion.course_id == course.id)
        lesson_ids = select(Lesson.id).where(Lesson.module_id.in_(module_ids))
        section_ids = select(Section.id).where(Section.lesson_id.in_(lesson_ids))
        await purge(ContentBlock, ContentBlock.section_id.in_(section_ids))
        await purge(Section, Section.id.in_(section_ids))
        await purge(Lesson, Lesson.id.in_(lesson_ids))
        await purge(Module, Module.id.in_(module_ids))
        await purge(Enrollment, Enrollment.course_id == course.id)
    if course_ids:
        await purge(Course, Course.id.in_(course_ids))

    if user_ids:
        await purge(User, User.id.in_(user_ids))
    await db.flush()
    return {k: v for k, v in sorted(counts.items()) if v}


# ── command line ────────────────────────────────────────────────────────────


async def _run(url: str, *, reset: bool, confirm: bool, learner_password: str | None,
               designer_password: str | None) -> int:
    engine = create_async_engine(url)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as db:
            if reset:
                report = {"skipped": False, "counts": await reset_demo(db)}
                verb = "remove"
            else:
                report = await seed_demo(
                    db,
                    learner_password=learner_password or secrets.token_urlsafe(16),
                    designer_password=designer_password or secrets.token_urlsafe(16),
                )
                verb = "create"
            if report["skipped"]:
                print("  The demo designer already exists — nothing to do. "
                      "Run with --reset --confirm first to rebuild.")
                await db.rollback()
                return 0
            print(f"  rows to {verb}:")
            for table, n in report["counts"].items():
                print(f"    {table:<26} {n}")
            if not confirm:
                await db.rollback()
                print("\n  DRY RUN - nothing written. Re-run with --confirm to apply.")
                return 0
            await db.commit()
            print("\n  done.")
            if not reset:
                print(f"  learner login:  {LEARNER['email_address']}")
                print(f"  designer login: {DESIGNER['email_address']}")
            return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database-url", default=None,
                    help="defaults to DATABASE_URL, then the app's configured database")
    ap.add_argument("--confirm", action="store_true", help="write; omit for a dry run")
    ap.add_argument("--reset", action="store_true", help="remove every demo account and course")
    ap.add_argument("--learner-password", default=os.getenv("DEMO_LEARNER_PASSWORD"))
    ap.add_argument("--designer-password", default=os.getenv("DEMO_DESIGNER_PASSWORD"))
    a = ap.parse_args(argv)

    url = a.database_url or os.getenv("DATABASE_URL")
    if not url:
        from app.core.config import settings

        url = settings.DATABASE_URL
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    if a.confirm and not a.reset:
        for name, value in (("learner", a.learner_password), ("designer", a.designer_password)):
            if not value or len(value) < 8:
                raise SystemExit(
                    f"a {name} password of at least 8 characters is required to write: "
                    f"--{name}-password or DEMO_{name.upper()}_PASSWORD"
                )

    # Host and database only: the URL carries the credentials.
    print(f"  target: {url.split('@')[-1]}")
    return asyncio.run(_run(url, reset=a.reset, confirm=a.confirm,
                            learner_password=a.learner_password,
                            designer_password=a.designer_password))


if __name__ == "__main__":
    raise SystemExit(main())
