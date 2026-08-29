"""Seed the pilot's Agentic AI courses.

The rich per-course content lives in `app/db/course_content/` (one module per course),
composed with the helpers in `app/db/course_content_helpers.py`. Each course is deliberately
structured so a learner passes through content that elicits the four target affect states
(engaged / bored / confused / frustrated); section titles stay topic-natural so they do NOT
bias participants. Intended affect per section is documented in
`deploy/azure/AFFECT_SECTION_CODEBOOK.md`.

Idempotent by title. Re-run with reset to replace existing seeded courses:
    python -m app.db.seed_courses           # insert if missing
    python -m app.db.seed_courses --reset   # delete these courses (cascade) then re-insert
"""

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.db.course_content.building import build as build_building
from app.db.course_content.foundations import build as build_foundations
from app.db.course_content.java import build as build_java
from app.db.course_content.multiagent import build as build_multiagent
from app.db.course_content.warmup import build as build_warmup
from app.models.assessment import Assessment
from app.models.course import Course, Module


def _build_courses() -> list[Course]:
    # Pilot design: ALL participants take ONE study course — "Building AI Agents" — after the
    # neutral warm-up baseline. Building gives the best balance of the four affect states
    # (esp. the rare bored/confused/frustrated). `foundations.py` and `multiagent.py` are kept
    # in source (retired from the pilot, easily re-addable).
    #
    # BOOTSTRAP OVERRIDE (single-subject collection, Aug 2026): the two retired courses ARE
    # seeded here. One subject makes exactly one genuine pass, so Building alone (17 sections:
    # 3 confused / 2 bored / 3 frustrated) yields too few windows per minority class to train
    # on. Re-adding both takes the content universe to 49 sections — confused 3→9, bored 2→7,
    # frustrated 3→6. REVERT to `[build_warmup(), build_building()]` before the Phase A pilot,
    # which keeps the single-study-course design documented in AFFECT_SECTION_CODEBOOK.md.
    #
    # `java.py` is a SECOND SUBJECT DOMAIN (added Aug 2026). Every other section is Agentic AI, so
    # nothing until now tested whether grounded hints work on unfamiliar material — which is the
    # platform's core claim. It also carries two `exercise` sections, making the "Show answer"
    # affordance reachable (only 5 sections platform-wide had one).
    #
    # DECIDE BEFORE THE PHASE A PILOT whether Java stays in. It is not affect-balanced like the
    # study courses and it widens the content universe (49 -> ~57 sections), which changes the
    # per-class window counts the codebook assumes. Keeping it is a research-design choice, not a
    # default — see the REVERT note above.
    return [
        build_warmup(),
        build_building(),
        build_foundations(),
        build_multiagent(),
        build_java(),
    ]


# Titles this seeder MANAGES on `--reset`. A superset of what `_build_courses` creates: it
# keeps the two retired titles so a `--reset` DELETES them from any DB that still has them.
_TITLES = [
    "Getting Comfortable: A Warm-Up",
    "Foundations of Agentic AI",
    "Building AI Agents: Tools, Memory & Planning",
    "Multi-Agent Systems & Orchestration",
    "Java Essentials: From First Program to Objects",
]


async def reset_courses(db: AsyncSession) -> int:
    """Delete the seeded courses (cascade removes modules/lessons/sections/blocks)."""
    res = await db.execute(select(Course).where(Course.title.in_(_TITLES)))
    courses = res.scalars().all()
    for c in courses:
        await db.delete(c)
    await db.commit()
    return len(courses)


async def seed_courses(db: AsyncSession) -> list[str]:
    """Insert the courses if absent (idempotent by title). Returns created titles."""
    created = []
    for course in _build_courses():
        existing = await db.execute(select(Course).where(Course.title == course.title))
        if existing.scalar_one_or_none() is None:
            db.add(course)
            created.append(course.title)
    await db.commit()
    return created


async def seed_assessments(db: AsyncSession) -> list[str]:
    """Insert the pre/post assessments if absent (idempotent by title). Returns created titles.

    Runs AFTER `seed_courses` because an assessment attaches to a `module_id`, so the module must
    already exist. Skips silently when the module is missing rather than raising: a deployment that
    seeds only the warm-up course should not fail because a study assessment has nowhere to attach.
    """
    from app.db.assessment_content import building as building_assess

    created: list[str] = []
    module = (
        await db.execute(
            select(Module).where(Module.title == building_assess.MODULE_TITLE)
        )
    ).scalars().first()
    if module is None:
        return created

    for build in (building_assess.build_pre, building_assess.build_post):
        a = build()
        existing = await db.execute(select(Assessment).where(Assessment.title == a.title))
        if existing.scalar_one_or_none() is None:
            a.module_id = module.id
            db.add(a)
            created.append(a.title)
    await db.commit()
    return created


async def run_seed(reset: bool = False) -> None:
    async with async_session() as db:
        if reset:
            n = await reset_courses(db)
            print(f"Reset: deleted {n} existing course(s).")
        created = await seed_courses(db)
        if created:
            print(f"Seeded courses: {', '.join(created)}")
        else:
            print("All courses already exist — no changes.")

        # After courses: an assessment needs an existing `module_id` to attach to.
        assessments = await seed_assessments(db)
        if assessments:
            print(f"Seeded assessments: {', '.join(assessments)}")
        else:
            print("No assessments seeded (already present, or the study module is absent).")


if __name__ == "__main__":
    asyncio.run(run_seed(reset="--reset" in sys.argv))
