"""Learner profile logic + cold (Postgres) store (Story 4.5).

Pure transformations (`default_profile`, `apply_affect`, `skill_from_preassessment`) carry
no I/O and are unit-tested directly. The DB helpers operate on a caller-provided
`AsyncSession` (the WS connection's session, passed transiently through AgentState).
"""

from __future__ import annotations

import uuid as uuid_mod
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentAttempt
from app.models.learner_profile import LearnerProfile

_AFFECT_HISTORY_CAP = 20


def default_profile() -> dict[str, Any]:
    """Canonical empty profile shape (architecture.md learner_profile fields)."""
    return {
        "affect_state": None,
        "affect_history": [],
        "skill_level": "intermediate",
        "topic_mastery": {},        # section_id -> mastery (filled by Story 4.6)
        "format_preferences": {},
        "session_count": 0,
        "cycle_count": 0,
        "updated_at": None,
    }


def skill_from_preassessment(ratio: float) -> str:
    """Map a pre-assessment score ratio to a coarse skill level."""
    if ratio < 0.5:
        return "low"
    if ratio < 0.8:
        return "intermediate"
    return "advanced"


def apply_affect(
    profile: dict[str, Any], affect_state: str | None, cycle_number: int | None, now_ms: int
) -> dict[str, Any]:
    """Fold the current affect into the profile, returning a NEW dict.

    A None/missing affect (empty or errored cycle) leaves affect fields unchanged but still
    stamps `updated_at`, so the profile reflects that the cycle ran.
    """
    p = dict(profile)
    history = list(p.get("affect_history") or [])
    if affect_state:
        history.append(affect_state)
        p["affect_history"] = history[-_AFFECT_HISTORY_CAP:]
        p["affect_state"] = affect_state
        p["cycle_count"] = int(p.get("cycle_count", 0)) + 1
    else:
        p["affect_history"] = history
    p["updated_at"] = now_ms
    return p


def _as_uuid(user_id: Any) -> uuid_mod.UUID | None:
    if isinstance(user_id, uuid_mod.UUID):
        return user_id
    try:
        return uuid_mod.UUID(str(user_id))
    except (ValueError, AttributeError, TypeError):
        return None


async def load_cold(db: AsyncSession, user_id: Any) -> dict[str, Any] | None:
    uid = _as_uuid(user_id)
    if uid is None:
        return None
    row = (
        await db.execute(select(LearnerProfile).where(LearnerProfile.user_id == uid))
    ).scalar_one_or_none()
    return dict(row.profile) if row and row.profile else None


async def persist_cold(db: AsyncSession, user_id: Any, profile: dict[str, Any]) -> None:
    uid = _as_uuid(user_id)
    if uid is None:
        return
    row = (
        await db.execute(select(LearnerProfile).where(LearnerProfile.user_id == uid))
    ).scalar_one_or_none()
    if row is None:
        db.add(LearnerProfile(user_id=uid, profile=profile))
    else:
        row.profile = profile
    await db.commit()


async def init_from_preassessment(db: AsyncSession, user_id: Any) -> dict[str, Any]:
    """Default profile with `skill_level` inferred from the learner's pre-assessments."""
    prof = default_profile()
    uid = _as_uuid(user_id)
    if uid is None:
        return prof
    rows = (
        await db.execute(
            select(AssessmentAttempt.score, AssessmentAttempt.max_score)
            .join(Assessment, AssessmentAttempt.assessment_id == Assessment.id)
            .where(AssessmentAttempt.user_id == uid, Assessment.assessment_type == "pre")
        )
    ).all()
    total = sum(r[0] for r in rows)
    max_total = sum(r[1] for r in rows)
    if max_total > 0:
        prof["skill_level"] = skill_from_preassessment(total / max_total)
    return prof


async def load_or_init(db: AsyncSession, user_id: Any) -> dict[str, Any]:
    """Cold profile if present, else a pre-assessment-initialized default."""
    cold = await load_cold(db, user_id)
    if cold is not None:
        return cold
    return await init_from_preassessment(db, user_id)
