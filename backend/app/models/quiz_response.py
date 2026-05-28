from sqlalchemy import Boolean, Column, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class QuizBlockResponse(BaseModel):
    __tablename__ = "quiz_responses"
    __table_args__ = (
        UniqueConstraint("user_id", "content_block_id", name="uq_quiz_response_user_block"),
    )

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content_block_id = Column(UUID(as_uuid=True), ForeignKey("content_blocks.id", ondelete="CASCADE"), nullable=False, index=True)
    selected_answers = Column(JSON, nullable=False)
    is_correct = Column(Boolean, nullable=False)
