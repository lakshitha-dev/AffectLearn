"""One sitting of one participant in the in-person pilot (migration 034).

The platform's `session_id` is a connection-level id that survives reconnects and restarts; it is
not "Participant 7 sat down at 10:00 and finished at 11:10". The pilot needs that sitting as a
record of its own -- the participant code, the arm, the protocol and consent versions in force, the
configuration version at the start, the device used, when it started and ended and why it ended
(completed, withdrew, technical failure), and any deviation from the protocol -- because those are
what a CONSORT-style account of the study, and the exclusion rules of its analysis, are built from.

Created and closed by the facilitator through the admin API. It holds no name: the participant code
is the only identifier, and the link from code to person stays on paper.
"""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import BaseModel

#: Domain of the pseudonymous pilot accounts (`p007@pilot.affectlearn.io`). A subdomain of the
#: platform's own seeded-account domain, so no participant's real address is ever stored and no
#: third party's domain is used. Not `.invalid`: the login schema's e-mail validator rejects reserved
#: names, which made every pilot account impossible to sign in to.
PILOT_EMAIL_DOMAIN = "pilot.affectlearn.io"


def pilot_email(code: str) -> str:
    """The login e-mail of the pilot account for a participant code (P007 -> p007@...)."""
    return f"{code.lower()}@{PILOT_EMAIL_DOMAIN}"


#: Why a sitting ended. Anything else is refused, so the counts in the participant-flow diagram
#: are counts of known categories.
END_REASONS = ("completed", "withdrawn", "technical", "other")


class PilotSession(BaseModel):
    __tablename__ = "pilot_sessions"

    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    participant_code = Column(String(16), nullable=False, index=True)
    group = Column(String(32), nullable=True)
    phase = Column(String(32), nullable=True)
    protocol_version = Column(String(32), nullable=True)
    consent_version = Column(String(32), nullable=True)
    config_version_at_start = Column(Integer, nullable=True)
    #: Browser, screen and camera setup noted by the facilitator. Never a name.
    device = Column(JSON, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    end_reason = Column(String(16), nullable=True)
    deviation_notes = Column(Text, nullable=True)
