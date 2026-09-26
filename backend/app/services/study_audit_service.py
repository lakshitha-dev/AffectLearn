"""Research-integrity checks over the A/B assignment (FR50), and the phase transition log.

WHY THESE ARE READS AND NOT CONSTRAINTS

Some of what FR50 asks about is already impossible by construction: `study_groups.user_id` is
UNIQUE, so a learner cannot literally hold two group rows. Checking anyway is the point — an audit
that only reports what it expects to find tells you nothing about the day the constraint is
dropped in a migration, or the data is loaded from a backup, or the analysis is run against a
database that is not this one. A check that can only pass is not a check.

The one that can genuinely fail is contamination: a control-group learner who received an
adaptation. Nothing in the schema prevents it — the gate is application logic, and Section 4.5 of
the paper records that gate defects are exactly the kind of thing that goes unnoticed until
something reports on them.

PHASE HISTORY WITHOUT A HISTORY TABLE

`study_phase` is a singleton row holding the CURRENT phase and the last transition timestamp, so
it cannot answer "when did each phase start, and who started it". `set_phase` has always emitted a
`phase_transition` research event carrying `{from, to, transitioned_at, actor_id}` on a real
change, so the history is already recorded — it simply had no reader. Reconstructing it from the
event log rather than adding a table keeps one source of truth for what happened.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistance_event import AssistanceEvent
from app.models.research_event import ResearchEvent
from app.models.study_group import StudyGroup
from app.models.user import Role, User
from app.services import demo_scope

#: Event type written by `study_service.set_phase` on a real phase change.
PHASE_TRANSITION = "phase_transition"


async def phase_history(db: AsyncSession) -> list[dict[str, Any]]:
    """Every recorded phase transition, newest first, with who made it.

    `actor_id` is resolved to a name here because "who moved the study into Phase B" is the
    question the log answers, and a UUID does not answer it. An actor who has since been deleted
    resolves to None rather than dropping the row — the transition still happened.
    """
    rows = (
        await db.execute(
            select(ResearchEvent)
            .where(ResearchEvent.event_type == PHASE_TRANSITION)
            .order_by(ResearchEvent.timestamp.desc())
        )
    ).scalars().all()

    actor_ids: set[uuid.UUID] = set()
    for row in rows:
        raw = (row.payload or {}).get("actor_id")
        if raw:
            try:
                actor_ids.add(uuid.UUID(str(raw)))
            except (ValueError, AttributeError):
                continue

    names: dict[str, str] = {}
    if actor_ids:
        for user in (
            await db.execute(select(User).where(User.id.in_(actor_ids)))
        ).scalars().all():
            names[str(user.id)] = f"{user.first_name} {user.last_name}".strip()

    history = []
    for row in rows:
        payload = row.payload or {}
        actor_id = payload.get("actor_id")
        history.append(
            {
                "from_phase": payload.get("from"),
                "to_phase": payload.get("to"),
                "transitioned_at": payload.get("transitioned_at"),
                "timestamp": row.timestamp,
                "actor_id": actor_id,
                "actor_name": names.get(str(actor_id)) if actor_id else None,
            }
        )
    return history


async def audit(db: AsyncSession) -> list[dict[str, Any]]:
    """Run the research-integrity checks and report pass/fail per check.

    Each entry is `{id, label, passed, detail, count}`. `count` is the number of offending rows,
    so a failure says how bad rather than only that it happened.
    """
    checks: list[dict[str, Any]] = []

    # Seeded demo accounts (`services/demo_scope.py`) are not study participants. Every check
    # leaves them out, consistently: excluding them from one set but not another would make a
    # check count them as, say, unassigned learners with data.
    demo = set(await demo_scope.demo_user_ids(db))

    def real(stmt, column):
        return stmt.where(column.notin_(demo)) if demo else stmt

    # 1. A learner in two groups. Prevented by a UNIQUE constraint; checked anyway — see module
    #    docstring for why a check that can only pass is not worth having.
    duplicate_rows = (
        await db.execute(
            select(func.count())
            .select_from(
                real(select(StudyGroup.user_id), StudyGroup.user_id)
                .group_by(StudyGroup.user_id)
                .having(func.count(StudyGroup.id) > 1)
                .subquery()
            )
        )
    ).scalar_one()
    checks.append(
        {
            "id": "no_learner_in_two_groups",
            "label": "No learner is assigned to more than one group",
            "passed": duplicate_rows == 0,
            "count": int(duplicate_rows or 0),
            "detail": (
                "Enforced by a unique constraint on study_groups.user_id."
                if duplicate_rows == 0
                else "Duplicate assignments found — the cohorts are not disjoint."
            ),
        }
    )

    # 2. Contamination: a CONTROL learner who was actually shown an adaptation. This is the check
    #    that can genuinely fail — the gate is application logic, not a constraint.
    control_ids = set(
        (
            await db.execute(
                select(StudyGroup.user_id).where(StudyGroup.group == "control")
            )
        )
        .scalars()
        .all()
    ) - demo
    contaminated = 0
    if control_ids:
        contaminated = (
            await db.execute(
                select(func.count(func.distinct(AssistanceEvent.learner_id))).where(
                    AssistanceEvent.learner_id.in_(control_ids)
                )
            )
        ).scalar_one()
    checks.append(
        {
            "id": "no_control_adaptations",
            "label": "No control-group learner has received an adaptation",
            "passed": contaminated == 0,
            "count": int(contaminated or 0),
            "detail": (
                "The control arm is clean."
                if contaminated == 0
                else (
                    "Control-group learners have adaptation records. Their sessions are "
                    "contaminated and cannot be analysed as controls."
                )
            ),
        }
    )

    # 3. Unassigned learners who have nonetheless generated data. `get_group` defaults an
    #    unassigned account to `control`, so these rows would silently be POOLED INTO the control
    #    arm by that default — which is why they need surfacing rather than ignoring.
    assigned_ids = set(
        (await db.execute(select(StudyGroup.user_id))).scalars().all()
    )
    unassigned_active_stmt = real(
        select(func.count(func.distinct(AssistanceEvent.learner_id))),
        AssistanceEvent.learner_id,
    )
    if assigned_ids:
        unassigned_active_stmt = unassigned_active_stmt.where(
            AssistanceEvent.learner_id.notin_(assigned_ids)
        )
    unassigned_active = (await db.execute(unassigned_active_stmt)).scalar_one()
    checks.append(
        {
            "id": "no_unassigned_with_data",
            "label": "Every learner with recorded data has a group assignment",
            "passed": unassigned_active == 0,
            "count": int(unassigned_active or 0),
            "detail": (
                "All recorded learners are assigned."
                if unassigned_active == 0
                else (
                    "Unassigned learners have generated data. They default to `control` at "
                    "read time, so this data would silently join the control arm."
                )
            ),
        }
    )

    # 4. Coverage: learners with no assignment at all. Not an integrity failure before the pilot
    #    starts — it is the ordinary state — so it is reported as a count, and only fails once
    #    assignments are locked, which is the point at which the cohorts are supposed to be final.
    # Counted as "learner accounts NOT in the assignment table", not as
    # (learner count - assignment count): the two sets are not the same population, because an
    # assignment can exist against a non-learner account. Subtracting the totals would cancel a
    # designer's assignment against an unassigned learner and report a clean study.
    unassigned_stmt = real(
        select(func.count()).select_from(User).where(User.role == Role.learner), User.id
    )
    if assigned_ids:
        unassigned_stmt = unassigned_stmt.where(User.id.notin_(assigned_ids))
    unassigned = int((await db.execute(unassigned_stmt)).scalar_one() or 0)

    locked = (
        await db.execute(
            real(select(func.count()).select_from(StudyGroup), StudyGroup.user_id)
            .where(StudyGroup.locked_at.isnot(None))
        )
    ).scalar_one()
    checks.append(
        {
            "id": "all_learners_assigned",
            "label": "Every learner account has a group assignment",
            "passed": unassigned <= 0 or not locked,
            "count": max(unassigned, 0),
            "detail": (
                "All learner accounts are assigned."
                if unassigned <= 0
                else (
                    f"{unassigned} learner account(s) have no assignment. "
                    + (
                        "Assignments are locked, so these cannot now be corrected."
                        if locked
                        else "Assign them before locking the cohorts."
                    )
                )
            ),
        }
    )

    return checks
