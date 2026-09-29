"""What a learner has consented to, and therefore what the server may capture from them.

The browser decides whether to open the camera and whether to start the listeners, but the
browser is not where consent can be enforced: a stale tab, a second device or a hand-built client
can send a `facial_features` or `behavioral_window` message regardless. Before this module nothing
on the server read `consent_given_at` or `webcam_enabled` at all, so capture from a learner who had
never consented, or who had switched the camera off, was processed and stored like any other.

Scopes:
  * participation  -- `consent_given_at` is set and `consent_withdrawn_at` is not. Required for any
                      research capture.
  * webcam         -- `webcam_enabled`, the learner's camera choice. Facial features need it.
  * behavioural    -- mouse / keyboard-category / scroll / visibility windows, and the performance
                      window. On by default for a participant: it is the study's core channel.
  * raw_interaction -- storing the raw timed events of a window, not just the features derived
                      from them. Off unless the learner opted in.

`consent_scopes` is NULL for learners who consented before scopes existed; they get the defaults
below, which are exactly what was in force when they agreed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: The consent text currently shown by the onboarding wizard. Bump it with the text, so each
#: record names the wording its learner actually saw.
CURRENT_CONSENT_VERSION = "2026-09-pilot-v1"

SCOPE_BEHAVIOURAL = "behavioural"
SCOPE_RAW_INTERACTION = "raw_interaction"
SCOPE_DEFAULTS: dict[str, bool] = {SCOPE_BEHAVIOURAL: True, SCOPE_RAW_INTERACTION: False}

#: Which scope each inbound WebSocket message needs, beyond participation.
MESSAGE_SCOPES: dict[str, str | None] = {
    "facial_features": "webcam",
    "behavioral_window": SCOPE_BEHAVIOURAL,
    "performance_window": SCOPE_BEHAVIOURAL,
    "self_report": None,
    "adaptation_probe": None,
    "adaptation_event": None,
}


def normalise_scopes(scopes: Any) -> dict[str, bool]:
    """Known scopes only, as booleans, with the defaults filled in."""
    out = dict(SCOPE_DEFAULTS)
    if isinstance(scopes, dict):
        for key in SCOPE_DEFAULTS:
            if key in scopes and scopes[key] is not None:
                out[key] = bool(scopes[key])
    return out


@dataclass(frozen=True)
class ConsentState:
    participating: bool
    webcam: bool
    scopes: dict[str, bool]

    @classmethod
    def of(cls, user: Any) -> "ConsentState":
        participating = (
            getattr(user, "consent_given_at", None) is not None
            and getattr(user, "consent_withdrawn_at", None) is None
        )
        return cls(
            participating=participating,
            webcam=bool(getattr(user, "webcam_enabled", False)),
            scopes=normalise_scopes(getattr(user, "consent_scopes", None)),
        )

    def refusal(self, msg_type: str) -> str | None:
        """Why this message may not be captured, or None if it may.

        Only message types in `MESSAGE_SCOPES` are capture; anything else (heartbeat, ui_event,
        help_request, adaptation_interaction) is not checked here.
        """
        if msg_type not in MESSAGE_SCOPES:
            return None
        if not self.participating:
            return "no_consent"
        scope = MESSAGE_SCOPES[msg_type]
        if scope == "webcam":
            return None if self.webcam else "webcam_not_consented"
        if scope is not None and not self.scopes.get(scope, False):
            return f"{scope}_not_consented"
        return None

    @property
    def raw_interaction(self) -> bool:
        return self.participating and self.scopes.get(SCOPE_RAW_INTERACTION, False)
