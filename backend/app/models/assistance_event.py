"""Durable ledger of every piece of help offered to a learner (migration 023).

WHY A TABLE, WHEN research_events ALREADY HAS THIS

`research_events` records the chain — `strategy_decided`, `adaptation_triggered`,
`adaptation_delivered`, `adaptation_interaction` — and since the intervention-lifecycle work it
records the hint text and the strategist's reason too. That is the right home for it as RESEARCH
data: append-only, sequence-numbered, filterable by phase and cohort.

It is the wrong home for a PRODUCT feature. Four reasons, all structural:

* It arrives on a best-effort path. `research_logger.emit` publishes to a Redis stream that a
  background worker drains; when Redis is down the event degrades to a log line and is gone. A
  learner's own history of the help they received must not disappear because a cache blinked.
* One intervention is spread across four rows keyed by `(session_id, cycle_number)`, so the
  simplest question anyone will ask — "show me the hints this learner got" — is a four-way
  self-join before it is a query.
* Everything interesting lives in `payload`, an unindexed JSON column. Filtering by action type
  or dismissal is a scan of the whole research corpus.
* The outcome is not in it at all, and cannot be: the answer a learner gives NEXT arrives minutes
  later on a different transport (a REST quiz submission, not the WebSocket cycle).

So this table is the queryable projection: one row per intervention, written at delivery, updated
in place when the learner responds and again when they next answer a question. `research_events`
remains the immutable record; this is the one you can serve a page from.

WHAT THE OUTCOME COLUMNS DO AND DO NOT CLAIM

`outcome_attempt_id` / `outcome_is_correct` record the first answer the learner submitted while
this help was on screen, joined by the `assistance_id` the client echoes back on the attempt.

That is an ASSOCIATION and the naming is deliberate. The learner may have solved it despite the
hint, ignored it entirely, or been helped by re-reading the section instead. Nothing here licenses
"the hint caused the correct answer", and any surface presenting these must say which of the two
it is asserting. The same discipline the monitor already applies to affect state after an
intervention — labelled as sequence, not outcome — applies here.
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import BaseModel

#: What a learner did with an offer of help, as sent on `adaptation_interaction`.
INTERACTIONS = ("accepted", "dismissed", "applied")


class AssistanceEvent(BaseModel):
    __tablename__ = "assistance_events"

    #: The server-issued id `deliver_node` mints and sends with the adaptation. Unique: it is the
    #: key the client echoes back on both the interaction and the following quiz attempt, so a
    #: duplicate would silently split one intervention's response across two rows.
    adaptation_id = Column(String(64), nullable=False, unique=True, index=True)

    learner_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    session_id = Column(String(64), nullable=True, index=True)
    cycle_number = Column(Integer, nullable=False, default=0)

    # ── where in the course ────────────────────────────────────────────────────
    # SET NULL rather than CASCADE: a designer deleting a section must not erase the evidence
    # that learners needed help in it. The row survives and stops pointing at a ghost.
    course_id = Column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    section_id = Column(
        UUID(as_uuid=True), ForeignKey("sections.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # ── what triggered it ──────────────────────────────────────────────────────
    affect_state = Column(String(16), nullable=True)
    #: Which channel the gate ruled on. The two channels have different confidence floors, so a
    #: confidence is uninterpretable without knowing which one produced it.
    affect_source = Column(String(32), nullable=True)
    affect_confidence = Column(Float, nullable=True)
    #: The GATE_* constant. Deliveries are all `ok` by definition; the column exists so that
    #: withheld cycles can be recorded here too if that is ever wanted, without a migration.
    gate_reason = Column(String(32), nullable=True)

    # ── what was decided, and why ──────────────────────────────────────────────
    action_type = Column(String(32), nullable=False)
    urgency = Column(String(16), nullable=True)
    #: The strategist's stated reason. INTERNAL — never rendered to a learner: it describes them
    #: in the third person and reads as surveillance rather than help.
    rationale = Column(Text, nullable=True)

    # ── what the learner actually saw ──────────────────────────────────────────
    hint_text = Column(Text, nullable=True)
    variant = Column(String(50), nullable=True)
    #: True when an LLM wrote it, False when the deterministic fallback did. The distinction is
    #: the whole of RQ3 on the delivered side: production currently has no GPU quota, so most
    #: rows are expected to be fallbacks and a surface that hides that would misreport the system.
    generated = Column(Boolean, nullable=False, default=False)
    fallback = Column(Boolean, nullable=False, default=False)
    fallback_reason = Column(String(64), nullable=True)

    # ── delivery and response ──────────────────────────────────────────────────
    #: Null when the socket was gone at send time. A generated-but-undelivered offer is a
    #: different fact from one never generated, and both are different from one dismissed.
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    delivery_failed = Column(Boolean, nullable=False, default=False)
    interaction = Column(String(16), nullable=True, index=True)
    interacted_at = Column(DateTime(timezone=True), nullable=True)

    # ── what happened next (association, not cause — see the module docstring) ──
    outcome_attempt_id = Column(
        UUID(as_uuid=True), ForeignKey("quiz_attempts.id", ondelete="SET NULL"),
        nullable=True,
    )
    outcome_is_correct = Column(Boolean, nullable=True)
    outcome_resolved_at = Column(DateTime(timezone=True), nullable=True)

    # ── study partitioning ─────────────────────────────────────────────────────
    phase = Column(String(32), nullable=True, index=True)
    group = Column(String(32), nullable=True, index=True)
