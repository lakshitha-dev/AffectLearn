"""Append-only record of every in-lesson quiz/exercise submission (migration 022).

WHY THIS EXISTS

`quiz_responses` is `UNIQUE(user_id, content_block_id)` and its route returns the existing row
on a repeat, so the FIRST answer wins and every later one is discarded. A learner who answers
wrongly, receives a hint, and then answers correctly leaves a record that says only "wrong".

That makes four things unanswerable from the durable tables: how many attempts a question took,
which mistakes repeat, how long each attempt took, and -- the one the study turns on -- whether
a learner succeeded AFTER being helped. `research_events` carries a `quiz_submitted` event per
submission, but that is an append-only research log drained from Redis on a best-effort path, not
a store a product feature may depend on; a learner's own answer history should not vanish because
Redis blinked.

RELATIONSHIP TO `quiz_responses`

Both are kept, deliberately. `quiz_responses` stays the per-block SUMMARY that
`progress_service` counts for "quizzes answered / correct", with its first-answer-wins semantics
UNCHANGED. Redefining that metric would silently move every learner's reported accuracy, and
changing an outcome measure's meaning partway through a study is exactly what makes results
unusable. Analytics that want latest-answer or best-answer semantics compose them from the
attempts here, where the choice is explicit rather than baked into a constraint.

THE ASSISTANCE LINK

`assistance_id` is the server-issued `adaptation_id` of the help that was on screen when the
learner answered, echoed back by the client. It is the join that turns "a hint was shown" into
"a hint was shown and the next attempt was correct". Nullable, and null for the overwhelming
majority of attempts: most answers follow no intervention at all.
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import BaseModel


class QuizAttempt(BaseModel):
    __tablename__ = "quiz_attempts"

    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    content_block_id = Column(
        UUID(as_uuid=True), ForeignKey("content_blocks.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    #: Denormalised from the block's parent so per-section aggregates need no join. Nullable
    #: because the client has always sent it optionally (see `QuizResponseCreate`).
    section_id = Column(
        UUID(as_uuid=True), ForeignKey("sections.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    #: 1-based, per (user, block). Assigned server-side by counting existing rows, never trusted
    #: from the client -- a client-supplied ordinal would let a retry silently overwrite history.
    attempt_number = Column(Integer, nullable=False, default=1)
    selected_answers = Column(JSON, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    #: Time from first seeing the question to submitting. The deliberation/frustration probe, and
    #: what makes "faster after the hint" measurable.
    response_time_ms = Column(Integer, nullable=True)
    #: Server-issued `adaptation_id` of the help on screen at submission. See the module docstring.
    assistance_id = Column(String(64), nullable=True, index=True)
    submitted_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
