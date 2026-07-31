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
from app.db.course_content.warmup import build as build_warmup
from app.models.course import Course


def _build_courses() -> list[Course]:
    # Pilot design: ALL participants take ONE study course — "Building AI Agents" — after the
    # neutral warm-up baseline. Building gives the best balance of the four affect states
    # (esp. the rare bored/confused/frustrated). `foundations.py` and `multiagent.py` are kept
    # in source (retired from the pilot, easily re-addable) but are NOT seeded.
    return [build_warmup(), build_building()]


# Titles this seeder MANAGES on `--reset`. A superset of what `_build_courses` creates: it
# keeps the two retired titles so a `--reset` DELETES them from any DB that still has them.
_TITLES = [
    "Getting Comfortable: A Warm-Up",
    "Foundations of Agentic AI",
    "Building AI Agents: Tools, Memory & Planning",
    "Multi-Agent Systems & Orchestration",
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


if __name__ == "__main__":
    asyncio.run(run_seed(reset="--reset" in sys.argv))
