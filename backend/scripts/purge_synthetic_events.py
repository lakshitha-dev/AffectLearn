"""Remove synthetic verification traffic from the research record.

WHY THIS EXISTS

Deploying the geometry channel was verified by injecting `facial_features` payloads over the
WebSocket with `face_ratio: 1.0` and `face_absent: false`. Those cycles are indistinguishable from
genuine learner cycles in `research_events` -- the table has no origin field -- so they were
written to the research record and appeared on the admin Pipeline Monitor as a learner sitting in
front of a camera at 100% face presence, with no camera open and no course started.

This removes them. It is a one-off repair, deliberately a script rather than an admin route: an
endpoint that deletes research events is a standing liability, and this needs to run once.

WHAT IT REMOVES, AND WHY THE PROFILE MATTERS MORE THAN THE EVENTS

Two things, both scoped to explicit session ids rather than a time range, so no genuine row can be
caught by a boundary:

  * `research_events` rows for the named sessions.
  * The learner's `affect_history`, `affect_history_by_source` and `cycle_count`.

The profile reset is the part with behavioural consequences. `_AFFECT_HISTORY_CAP` is 20
(`profile_service.py`), and the injected run appended 17 `bored` entries, so the adaptation gate's
consecutive-cycle condition would currently be satisfiable by a single genuine detection landing on
top of stale synthetic ones -- firing an intervention that no real evidence supports.

    python scripts/purge_synthetic_events.py --sessions a,b,c --learner <uuid>   # dry run
    python scripts/purge_synthetic_events.py --sessions a,b,c --learner <uuid> --confirm
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select, update  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.learner_profile import LearnerProfile  # noqa: E402
from app.models.research_event import ResearchEvent  # noqa: E402

# Keys reset on the learner profile. `affect_state` is left alone: it is a single current value
# that the next real cycle overwrites, and clearing it would make the profile look like a learner
# who has never been seen rather than one whose history was repaired.
_PROFILE_KEYS = ("affect_history", "affect_history_by_source", "cycle_count")


async def run(db_url: str, sessions: list[str], learner: str | None, confirm: bool) -> int:
    engine = create_async_engine(db_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        q = select(ResearchEvent).where(ResearchEvent.session_id.in_(sessions))
        if learner:
            q = q.where(ResearchEvent.learner_id == learner)
        rows = (await db.execute(q)).scalars().all()

        by_type: dict[str, int] = {}
        by_session: dict[str, int] = {}
        for r in rows:
            by_type[r.event_type] = by_type.get(r.event_type, 0) + 1
            by_session[r.session_id or "?"] = by_session.get(r.session_id or "?", 0) + 1

        print(f"  {len(rows)} research_events matched")
        for t, n in sorted(by_type.items(), key=lambda kv: -kv[1]):
            print(f"    {t:<32} {n}")
        print("  by session:")
        for s, n in by_session.items():
            print(f"    {s:<36} {n}")

        prof = None
        if learner:
            prof = (await db.execute(
                select(LearnerProfile).where(LearnerProfile.user_id == learner)
            )).scalar_one_or_none()
            if prof:
                p = dict(prof.profile or {})
                hist = list(p.get("affect_history") or [])
                print(f"\n  learner profile: affect_history has {len(hist)} entries "
                      f"{hist[-5:] if hist else ''}")
                print(f"    by_source keys: {list((p.get('affect_history_by_source') or {}).keys())}")
                print(f"    cycle_count: {p.get('cycle_count')}")
            else:
                print(f"\n  no learner_profiles row for {learner}")

        if not confirm:
            print("\n  DRY RUN - nothing deleted. Re-run with --confirm to apply.")
            return 0

        if rows:
            stmt = delete(ResearchEvent).where(ResearchEvent.session_id.in_(sessions))
            if learner:
                stmt = stmt.where(ResearchEvent.learner_id == learner)
            await db.execute(stmt)

        if prof:
            p = dict(prof.profile or {})
            for k in _PROFILE_KEYS:
                p.pop(k, None)
            await db.execute(
                update(LearnerProfile)
                .where(LearnerProfile.user_id == learner)
                .values(profile=p)
            )

        await db.commit()

        left = (await db.execute(q)).scalars().all()
        print(f"\n  deleted. {len(left)} matching events remain (expected 0)")
        if prof:
            after = (await db.execute(
                select(LearnerProfile).where(LearnerProfile.user_id == learner)
            )).scalar_one_or_none()
            pa = dict(after.profile or {}) if after else {}
            print(f"  profile keys now: {sorted(pa.keys())}")
    await engine.dispose()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sessions", required=True,
                    help="comma-separated session ids to purge (explicit, never a time range)")
    ap.add_argument("--learner", default=None, help="restrict to this learner_id")
    ap.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    ap.add_argument("--confirm", action="store_true", help="actually delete; omit for a dry run")
    a = ap.parse_args()

    if not a.database_url:
        raise SystemExit("no --database-url and DATABASE_URL is unset")
    sessions = [s.strip() for s in a.sessions.split(",") if s.strip()]
    if not sessions:
        raise SystemExit("--sessions is empty; refusing to run unscoped")

    url = a.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    print(f"  target: {url.split('@')[-1]}")
    print(f"  sessions: {sessions}")
    print(f"  learner: {a.learner or '(any)'}\n")
    return asyncio.run(run(url, sessions, a.learner, a.confirm))


if __name__ == "__main__":
    raise SystemExit(main())
