"""Keep seeded demonstration data out of the research record.

`app/db/seed_demo.py` creates a demo learner, a demo designer and a background class so the
platform can be shown working with realistic data. Those accounts share the database with the
study's real participants, and every surface that feeds the thesis must leave them out: a demo
learner's seeded hints would otherwise be sampled for educator review, their events exported as
training data, and the background class's control/adaptive split counted in the study audit.

What is filtered, and where:
  * `research_export_service`  — the research export, gap audit and Phase A dataset.
  * `monitor_export_service`   — the monitor CSV download.
  * `study_audit_service`      — the A/B integrity checks.
  * `decision_review_service`  — the educator review sample and its total.
  * `gate_replay_service`      — the threshold sweep over recorded readings.

What is deliberately NOT filtered: the live monitor stream and its 24-hour aggregates. Those
describe what the system is doing right now, and showing the demo learner there is the point of
a demonstration. The seeded history is dated days in the past, outside that window, so it never
appears there; only a live session does.

The ids are loaded rather than sub-selected: `research_events.learner_id` is a string, and the
text form of a UUID differs by database (hyphenated on Postgres, bare hex on SQLite), so a SQL
cast would match on one and silently match nothing on the other. There are a dozen or so demo
accounts; the list is small.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def demo_user_ids(db: AsyncSession) -> list[uuid.UUID]:
    """Ids of every demo account, for filtering UUID columns."""
    return list((await db.execute(select(User.id).where(User.is_demo.is_(True)))).scalars().all())


async def demo_learner_id_strings(db: AsyncSession) -> list[str]:
    """The same ids in the string form `research_events.learner_id` stores."""
    return [str(uid) for uid in await demo_user_ids(db)]


def exclude_learners(stmt, learner_column, ids):
    """Drop rows whose learner is in `ids`. Rows with no learner are kept. No-op when empty."""
    if not ids:
        return stmt
    return stmt.where(learner_column.is_(None) | learner_column.notin_(list(ids)))
