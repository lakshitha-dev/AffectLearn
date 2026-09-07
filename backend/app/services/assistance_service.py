"""Write and read the assistance ledger (migration 023).

The ledger has three write points, spread across two transports, which is why it is a service
rather than route code:

* DELIVERY, on the WebSocket, when `deliver_node` has issued an `adaptation_id` and the socket
  send has either succeeded or failed.
* RESPONSE, on the WebSocket, when the learner accepts, dismisses or applies the offer.
* OUTCOME, over REST, minutes later, when the learner submits an answer carrying the same
  `assistance_id`.

FAILURE POSTURE

Recording help must never break the delivery of help. Every function returns None on failure
after logging, and none of them raise. Where a caller owns a transaction the function flushes and
leaves the commit alone; where it does not (the WebSocket has no request-scoped transaction), the
function commits its own row and rolls back on failure so a half-written ledger can never poison
the caller's session.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistance_event import AssistanceEvent

logger = structlog.get_logger(__name__)

#: `hint_text` is Text and unbounded in the database, but a generator fault should not be able to
#: write an unbounded row. Matches the cap the research event already applies.
_TEXT_CAP = 4000
_RATIONALE_CAP = 500


def _uuid_or_none(value: Any) -> uuid.UUID | None:
    """Coerce a coordinate to UUID, or None. Coordinates arrive as strings from the event
    envelope and as UUIDs from route code, and a bad one must not cost us the row."""
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


async def record_delivery(
    db: AsyncSession,
    *,
    adaptation_id: str,
    learner_id: Any,
    session_id: str | None,
    cycle_number: int,
    action_type: str,
    delivered: bool,
    hint_text: str | None = None,
    variant: str | None = None,
    urgency: str | None = None,
    rationale: str | None = None,
    affect_state: str | None = None,
    affect_source: str | None = None,
    affect_confidence: float | None = None,
    gate_reason: str | None = None,
    generated: bool = False,
    fallback: bool = False,
    fallback_reason: str | None = None,
    course_id: Any = None,
    section_id: Any = None,
    phase: str | None = None,
    group: str | None = None,
) -> AssistanceEvent | None:
    """Write the ledger row for one intervention. Commits. Never raises.

    `delivered=False` records an offer the gate produced and the learner never received, which is
    a different fact from one never produced and from one dismissed. Without it, a failed send is
    indistinguishable in the ledger from an adaptation that was never generated.
    """
    learner_uuid = _uuid_or_none(learner_id)
    if not adaptation_id or learner_uuid is None:
        logger.warning(
            "assistance_ledger_skipped",
            reason="missing_identity",
            adaptation_id=adaptation_id,
            learner_id=str(learner_id),
        )
        return None

    try:
        row = AssistanceEvent(
            adaptation_id=str(adaptation_id)[:64],
            learner_id=learner_uuid,
            session_id=(str(session_id)[:64] if session_id else None),
            cycle_number=int(cycle_number or 0),
            course_id=_uuid_or_none(course_id),
            section_id=_uuid_or_none(section_id),
            affect_state=affect_state,
            affect_source=affect_source,
            affect_confidence=(
                round(float(affect_confidence), 4) if affect_confidence is not None else None
            ),
            gate_reason=gate_reason,
            action_type=str(action_type)[:32],
            urgency=urgency,
            rationale=(str(rationale)[:_RATIONALE_CAP] if rationale else None),
            hint_text=(str(hint_text)[:_TEXT_CAP] if hint_text else None),
            variant=variant,
            generated=bool(generated),
            fallback=bool(fallback),
            fallback_reason=(str(fallback_reason)[:64] if fallback_reason else None),
            delivered_at=(func.now() if delivered else None),
            delivery_failed=not delivered,
            phase=phase,
            group=group,
        )
        db.add(row)
        await db.commit()
        return row
    except Exception:  # noqa: BLE001 — recording help must never break delivering it
        await _safe_rollback(db)
        logger.exception("assistance_ledger_write_failed", adaptation_id=str(adaptation_id))
        return None


async def record_interaction(
    db: AsyncSession, *, adaptation_id: str, interaction: str
) -> AssistanceEvent | None:
    """Record what the learner did with an offer. Commits. Never raises.

    Unknown ids are ignored rather than treated as an error: the id is client-supplied, and a
    response can legitimately arrive for a delivery whose ledger write failed.
    """
    try:
        row = (
            await db.execute(
                select(AssistanceEvent).where(
                    AssistanceEvent.adaptation_id == str(adaptation_id)
                )
            )
        ).scalar_one_or_none()
        if row is None:
            logger.debug("assistance_interaction_unmatched", adaptation_id=str(adaptation_id))
            return None

        row.interaction = str(interaction)[:16]
        row.interacted_at = func.now()
        await db.commit()
        return row
    except Exception:  # noqa: BLE001
        await _safe_rollback(db)
        logger.exception("assistance_interaction_failed", adaptation_id=str(adaptation_id))
        return None


async def resolve_outcome(
    db: AsyncSession, *, adaptation_id: str, attempt_id: Any, is_correct: bool
) -> AssistanceEvent | None:
    """Record the first answer submitted while this help was on screen. Never raises.

    Does NOT commit: the caller is the quiz route, which commits the attempt and this resolution
    together so the ledger can never claim an outcome for an attempt that was rolled back.

    FIRST answer only. A later attempt on the same block is a separate event and overwriting
    would silently convert "wrong after the hint, right two tries later" into "right after the
    hint" -- flattering, and false.

    This is an association, not a cause. See the model docstring.
    """
    try:
        row = (
            await db.execute(
                select(AssistanceEvent).where(
                    AssistanceEvent.adaptation_id == str(adaptation_id)
                )
            )
        ).scalar_one_or_none()
        if row is None or row.outcome_resolved_at is not None:
            return row

        row.outcome_attempt_id = _uuid_or_none(attempt_id)
        row.outcome_is_correct = bool(is_correct)
        row.outcome_resolved_at = func.now()
        await db.flush()
        return row
    except Exception:  # noqa: BLE001
        logger.exception("assistance_outcome_failed", adaptation_id=str(adaptation_id))
        return None


async def for_learner(
    db: AsyncSession, *, learner_id: Any, limit: int = 50, course_id: Any = None
) -> list[AssistanceEvent]:
    """A learner's help history, newest first. The read behind a learner-facing hint history."""
    stmt = select(AssistanceEvent).where(AssistanceEvent.learner_id == _uuid_or_none(learner_id))
    course_uuid = _uuid_or_none(course_id)
    if course_uuid is not None:
        stmt = stmt.where(AssistanceEvent.course_id == course_uuid)
    stmt = stmt.order_by(AssistanceEvent.created_at.desc()).limit(max(1, min(int(limit), 500)))
    return list((await db.execute(stmt)).scalars().all())


async def for_section(
    db: AsyncSession, *, section_id: Any, limit: int = 200
) -> list[AssistanceEvent]:
    """Every intervention in one section. The read behind per-section content effectiveness."""
    stmt = (
        select(AssistanceEvent)
        .where(AssistanceEvent.section_id == _uuid_or_none(section_id))
        .order_by(AssistanceEvent.created_at.desc())
        .limit(max(1, min(int(limit), 1000)))
    )
    return list((await db.execute(stmt)).scalars().all())


async def _safe_rollback(db: AsyncSession) -> None:
    """Roll back without letting the rollback itself propagate — a failed rollback on a dead
    connection would replace a logged write failure with an unhandled one at the caller."""
    try:
        await db.rollback()
    except Exception:  # noqa: BLE001
        logger.warning("assistance_ledger_rollback_failed", exc_info=True)


async def texts_shown_in_section(
    db: AsyncSession, *, learner_id: Any, section_id: Any, limit: int = 3
) -> list[str]:
    """What this learner has already been SHOWN in this section, newest first.

    The read behind "do not say the same thing twice". The escalation ladder stops the system
    repeating an ACTION, but nothing stopped it repeating a FRAMING: with the ladder enforced,
    `show_alternative` was observed returning the same "think of it like a friendly greeting"
    analogy the `show_hint` two rungs earlier had already used. The action escalated; the learner
    got the same explanation reworded.

    Scoped to one section because that is the unit the ladder is scoped to, and because a hint
    given about a different section is not a repetition — it is unrelated material.

    Empty text is filtered out rather than returned: a blank line in the prompt would spend tokens
    telling the model nothing.
    """
    stmt = (
        select(AssistanceEvent.hint_text)
        .where(
            AssistanceEvent.learner_id == _uuid_or_none(learner_id),
            AssistanceEvent.section_id == _uuid_or_none(section_id),
            AssistanceEvent.hint_text.isnot(None),
        )
        .order_by(AssistanceEvent.created_at.desc())
        .limit(max(1, min(int(limit), 10)))
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [t.strip() for t in rows if t and t.strip()]
