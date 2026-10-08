"""Seed the viva demonstration: one short course and one fresh learner account.

WHY THIS EXISTS

The live demonstration needs a course simple enough to follow in front of examiners, built so
each section shows one part of the system (`demo_content/python_loops.py`), and a learner who
logs in to it for the first time. The API cannot create either: learners must verify an email
address, which production does not let a script bypass, and only a seed can flag rows `is_demo`.

The learner starts FRESH: verified, but with no consent, so the first login goes through
onboarding (consent, webcam, calibration, questionnaire), and not enrolled, so enrolling is part
of the demonstration. They are in the `adaptive` study group, so help is delivered once the study
phase is `phase_b`. Rehearsing uses the account up; `--reset-learner` erases it and everything
recorded about it, and creates it again as new.

KEEPING IT OUT OF THE RESEARCH

The course and the learner are flagged `is_demo`, so `services/demo_scope.py` keeps them out of
the research export, the monitor CSV, the study audit, the review sample and the gate replay, and
real learners are never shown the course. The course belongs to the demo designer when
`seed_demo.py` has created her, so it appears in her editor and analytics.

USAGE (dry run by default — the seed runs in a transaction that is rolled back)

    python -m app.db.seed_viva                                  # preview against DATABASE_URL
    python -m app.db.seed_viva --confirm                        # write it
    python -m app.db.seed_viva --reset-learner --confirm        # erase the learner, recreate fresh
    python -m app.db.seed_viva --database-url postgresql://... --confirm

The learner's password comes from VIVA_LEARNER_PASSWORD or --learner-password. It is never
printed and never stored in the repo.

Idempotent: the course is matched by title and the learner by email; what exists is left alone.
The study phase and gate settings are reported, never changed.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import hash_password
from app.db.demo_content import python_loops
from app.db.demo_content.people import DEMO_DOMAIN, DESIGNER
from app.models.assistance_event import AssistanceEvent
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.quiz_attempt import QuizAttempt
from app.models.research_event import ResearchEvent
from app.models.section_progress import SectionProgress
from app.models.study_group import StudyGroup
from app.models.system_config import SystemConfig
from app.models.user import Role, User
from app.services import content_version_service, study_service

LEARNER = {
    "email_address": f"kavindu.silva@{DEMO_DOMAIN}",
    "first_name": "Kavindu",
    "last_name": "Silva",
    "age_range": "21-23",
    "degree_program": "BSc (Hons) Computer Science",
}


async def _find_user(db: AsyncSession, email: str) -> User | None:
    return (await db.execute(select(User).where(User.email_address == email))).scalar_one_or_none()


async def _seed_course(db: AsyncSession, counts: Counter) -> bool:
    """Add the course, its pre/post checks and a published version. False if it already exists."""
    exists = (await db.execute(
        select(Course.id).where(Course.title == python_loops.TITLE)
    )).scalar_one_or_none()
    if exists is not None:
        return False

    designer = await _find_user(db, DESIGNER["email_address"])
    owner = designer.id if designer is not None else None

    c = python_loops.build()
    c.is_demo = True
    c.created_by = owner
    db.add(c)
    counts["courses"] += 1
    for m in c.modules:
        counts["modules"] += 1
        for le in m.lessons:
            counts["lessons"] += 1
            for s in le.sections:
                counts["sections"] += 1
                counts["content_blocks"] += len(s.content_blocks)
    await db.flush()  # before the assessments that point at its module

    for check in (python_loops.build_pre(), python_loops.build_post()):
        check.module_id = c.modules[0].id
        db.add(check)
        counts["assessments"] += 1
        counts["assessment_questions"] += len(check.questions)
    await db.flush()

    version = await content_version_service.snapshot_on_publish(
        db, course_id=c.id, published_by=owner
    )
    if version is None:
        raise RuntimeError(f"could not snapshot {python_loops.TITLE!r}")
    counts["content_versions"] += 1
    return True


async def _seed_learner(db: AsyncSession, password: str, counts: Counter,
                        now: datetime) -> bool:
    """Add the fresh learner and their study group. False if they already exist."""
    if await _find_user(db, LEARNER["email_address"]) is not None:
        return False

    learner = User(
        id=uuid.uuid4(),
        email_address=LEARNER["email_address"],
        password_hash=hash_password(password),
        first_name=LEARNER["first_name"],
        last_name=LEARNER["last_name"],
        age_range=LEARNER["age_range"],
        degree_program=LEARNER["degree_program"],
        role=Role.learner,
        is_active=True,
        email_verified=True,
        consent_given_at=None,  # so the first login goes through onboarding
        webcam_enabled=False,  # chosen during onboarding
        is_demo=True,
        created_at=now,
        updated_at=now,
    )
    db.add(learner)
    counts["users"] += 1
    await db.flush()  # before the group that points at them
    db.add(StudyGroup(user_id=learner.id, group="adaptive"))
    counts["study_groups"] += 1
    await db.flush()
    return True


async def seed_viva(db: AsyncSession, *, learner_password: str,
                    now: datetime | None = None) -> dict[str, Any]:
    """Create the course and the learner where missing. Flushes but does NOT commit.

    Returns `{"course": bool, "learner": bool, "counts": {table: rows}}`, where each bool says
    whether that part was created on this run.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    counts: Counter = Counter()
    course_created = await _seed_course(db, counts)
    learner_created = await _seed_learner(db, learner_password, counts, now)
    return {"course": course_created, "learner": learner_created,
            "counts": dict(sorted(counts.items()))}


async def reset_learner(db: AsyncSession) -> dict[str, int]:
    """Delete the viva learner and everything recorded about them. Flushes but does NOT commit.

    The same erasure as `data_rights_service.erase_learner`: research events first, because they
    have no foreign key to `users`, then the user row, which the database cascades to everything
    else. That function commits, so it cannot be used inside a dry run.
    """
    learner = await _find_user(db, LEARNER["email_address"])
    if learner is None:
        return {}

    counts: dict[str, int] = {}
    for label, model, column in (
        ("assistance_events", AssistanceEvent, AssistanceEvent.learner_id),
        ("quiz_attempts", QuizAttempt, QuizAttempt.user_id),
        ("section_progress", SectionProgress, SectionProgress.user_id),
        ("enrollments", Enrollment, Enrollment.user_id),
    ):
        counts[label] = int((await db.execute(
            select(func.count(model.id)).where(column == learner.id)
        )).scalar_one() or 0)

    result = await db.execute(
        delete(ResearchEvent).where(ResearchEvent.learner_id == str(learner.id))
    )
    counts["research_events"] = result.rowcount or 0
    await db.delete(learner)
    await db.flush()
    counts["users"] = 1
    return counts


async def status(db: AsyncSession) -> dict[str, Any]:
    """What the demonstration depends on but this script never changes."""
    row = (await db.execute(
        select(SystemConfig).order_by(SystemConfig.created_at.asc()).limit(1)
    )).scalar_one_or_none()
    return {
        "phase": await study_service.get_phase(db),
        "gate_overrides": dict(row.values or {}) if row is not None else {},
        "llm_key_updated_at": row.llm_api_key_updated_at if row is not None else None,
        "demo_designer": await _find_user(db, DESIGNER["email_address"]) is not None,
    }


# ── command line ────────────────────────────────────────────────────────────


async def _run(url: str, *, reset: bool, confirm: bool, learner_password: str | None) -> int:
    engine = create_async_engine(url)
    session = async_sessionmaker(engine, expire_on_commit=False)
    password = learner_password or secrets.token_urlsafe(16)
    try:
        async with session() as db:
            if reset:
                removed = await reset_learner(db)
                print("  learner rows to remove:" if removed else "  no learner to remove")
                for table, n in removed.items():
                    print(f"    {table:<26} {n}")
            report = await seed_viva(db, learner_password=password)
            print(f"  course:  {'create' if report['course'] else 'already exists'}")
            print(f"  learner: {'create (fresh)' if report['learner'] else 'already exists'}")
            for table, n in report["counts"].items():
                print(f"    {table:<26} {n}")

            info = await status(db)
            print(f"\n  study phase:    {info['phase']}"
                  + ("" if info["phase"] == "phase_b" else "   <- help is only given in phase_b"))
            print(f"  gate overrides: {info['gate_overrides'] or 'none (app-setting defaults)'}")
            print(f"  LLM key set:    {info['llm_key_updated_at'] or 'not in admin settings'}")
            print(f"  demo designer:  {'present' if info['demo_designer'] else 'absent'}")

            if not confirm:
                await db.rollback()
                print("\n  DRY RUN - nothing written. Re-run with --confirm to apply.")
                return 0
            await db.commit()
            print("\n  done.")
            print(f"  learner login: {LEARNER['email_address']}")
            return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database-url", default=None,
                    help="defaults to DATABASE_URL, then the app's configured database")
    ap.add_argument("--confirm", action="store_true", help="write; omit for a dry run")
    ap.add_argument("--reset-learner", action="store_true",
                    help="erase the viva learner and everything recorded, then recreate them")
    ap.add_argument("--learner-password", default=os.getenv("VIVA_LEARNER_PASSWORD"))
    a = ap.parse_args(argv)

    url = a.database_url or os.getenv("DATABASE_URL")
    if not url:
        from app.core.config import settings

        url = settings.DATABASE_URL
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    if a.confirm and (not a.learner_password or len(a.learner_password) < 8):
        raise SystemExit("a learner password of at least 8 characters is required to write: "
                         "--learner-password or VIVA_LEARNER_PASSWORD")

    # Host and database only: the URL carries the credentials.
    print(f"  target: {url.split('@')[-1]}")
    return asyncio.run(_run(url, reset=a.reset_learner, confirm=a.confirm,
                            learner_password=a.learner_password))


if __name__ == "__main__":
    raise SystemExit(main())
