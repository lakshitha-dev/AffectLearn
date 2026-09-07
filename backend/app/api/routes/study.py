"""Pilot-study admin API: A/B group assignment + study-phase toggle (Story 6.1).

Mounted under `/admin/study`. Every route is admin-only (`require_role(Role.admin)`) and
uses the established `{error: {code, message}}` envelope. The routes are thin — auth →
validate → call `study_service` → shape response. The immutability rule (locked re-assign →
409 GROUP_LOCKED) and the `phase_transition` research event live in the service, not here.

The admin UI that drives these endpoints is Epic 8 scope (stories 8-2, 8-4); 6.1 lands only
the API + persistence + WS wiring those stories consume.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.models.study_group import StudyGroup
from app.models.user import Role, User
from app.schemas.base import PaginatedResponse
from app.schemas.study import (
    AuditCheck,
    GroupAssignmentResponse,
    GroupAssignRequest,
    LockResponse,
    PhaseResponse,
    PhaseSetRequest,
    PhaseTransitionEntry,
)
from app.services import study_audit_service, study_service

router = APIRouter()


def _assignment_response(row: StudyGroup) -> GroupAssignmentResponse:
    return GroupAssignmentResponse(
        id=row.id,
        user_id=row.user_id,
        group=row.group,
        locked_at=row.locked_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/study/groups", response_model=GroupAssignmentResponse)
async def assign_group(
    body: GroupAssignRequest,
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Assign (or pre-pilot correct) a learner's A/B group. Locked re-assign → 409."""
    user = (
        await db.execute(select(User).where(User.id == body.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "User not found"}},
        )

    try:
        row = await study_service.assign_group(db, body.user_id, body.group)
    except study_service.GroupAssignmentLockedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "GROUP_LOCKED",
                    "message": "Group assignment is locked; the pilot has begun",
                }
            },
        )
    return _assignment_response(row)


@router.get("/study/groups", response_model=PaginatedResponse)
async def list_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List A/B group assignments (paginated)."""
    offset = (page - 1) * page_size
    total = (
        await db.execute(select(func.count()).select_from(StudyGroup))
    ).scalar_one()
    rows = (
        await db.execute(
            select(StudyGroup)
            .order_by(StudyGroup.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()
    return PaginatedResponse(
        items=[_assignment_response(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/study/groups/lock", response_model=LockResponse)
async def lock_groups(
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Lock all assignments ("pilot begins"); returns the count locked."""
    locked = await study_service.lock_assignments(db)
    return LockResponse(locked_count=locked)


@router.get("/study/phase", response_model=PhaseResponse)
async def get_phase(
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Return the current global study phase + last transition timestamp."""
    state = await study_service.get_phase_state(db)
    return PhaseResponse(phase=state["phase"], transitioned_at=state["transitioned_at"])


@router.post("/study/phase")
async def set_phase(
    body: PhaseSetRequest,
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Set the global study phase. Emits `phase_transition` on a real change.

    Returns `{from, to, transitionedAt}` — `from`/`to` are the research-event contract
    keys and Python keywords, so the dict is serialized directly (no model coercion).
    """
    result = await study_service.set_phase(
        db, body.phase, actor_id=current_user.id
    )
    transitioned_at = result["transitioned_at"]
    return {
        "from": result["from"],
        "to": result["to"],
        "transitionedAt": transitioned_at.isoformat() if transitioned_at else None,
    }


@router.get("/study/phase/history", response_model=list[PhaseTransitionEntry])
async def phase_history(
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """When each phase began, and who began it (Story 8.4).

    The phase toggle had no log a coordinator could read. `study_phase` holds only the current
    value, so the answer to "when did we move to Phase B" lived solely in the research event
    stream, which the admin console does not query.
    """
    return [
        PhaseTransitionEntry(**entry)
        for entry in await study_audit_service.phase_history(db)
    ]


@router.get("/study/audit", response_model=list[AuditCheck])
async def study_audit(
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Research-integrity checks over the A/B assignment (FR50).

    Reports pass/fail per check rather than a single verdict: "the study is fine" is not
    actionable, and the checks fail for different reasons needing different responses.
    """
    return [AuditCheck(**check) for check in await study_audit_service.audit(db)]
