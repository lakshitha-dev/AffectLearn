"""Single-use email tokens for verification and password reset.

We never store the plaintext token — only its SHA-256 hash (see
``app.core.security.hash_url_token``). The plaintext travels in the emailed link;
verification hashes the incoming value and looks up the row.
"""

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel

# Token purposes — stored as plain strings (no native DB enum to keep migrations simple
# and SQLite-compatible for tests).
EMAIL_VERIFICATION = "email_verification"
PASSWORD_RESET = "password_reset"


class EmailToken(BaseModel):
    __tablename__ = "email_tokens"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(64), nullable=False, index=True)  # sha256 hex digest
    purpose = Column(String(32), nullable=False)  # EMAIL_VERIFICATION | PASSWORD_RESET
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
