"""Request/response shapes for the dev-only adaptation harness (`routes/dev_tools.py`)."""

from typing import Any, Literal

from pydantic import Field

from app.schemas.base import CamelModel


class SimulateCycleRequest(CamelModel):
    """One fabricated cycle.

    `action_type` is the fork. Given, the strategist is skipped and that exact action is built and
    pushed — the cheap path for checking that a card renders. Omitted, the real graph decides, and
    the answer may well be "nothing", which is the interesting case.
    """

    section_id: str
    affect_state: Literal["bored", "confused", "frustrated", "engaged"] = "confused"
    #: Provenance of the fabricated reading. Only a DECISIVE channel may intervene alone, so a
    #: value outside `DECISIVE_AFFECT_SOURCES` produces a `channel_advisory` verdict — which is
    #: the gate working, not the harness failing.
    affect_source: str = "behavioral_model"
    affect_confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    #: How many interventions the learner is pretended to have already had here, for this state.
    #: Selects the rung of the escalation ladder, which is the axis the UI never exercises.
    rung: int = Field(default=0, ge=0)
    #: Skip the strategist and deliver this action verbatim.
    action_type: str | None = None
    #: Text for a forced `action_type`. Ignored on the full-loop path, where the content is
    #: generated. Defaults to a string that says it is synthetic rather than imitating a hint.
    text: str | None = None
    #: Which trial arm to land in. `delivered` picks a cycle number whose withhold draw clears
    #: the rate; `withheld` picks one that does not; `any` takes the first cycle and reports
    #: whichever arm it fell in.
    arm: Literal["delivered", "withheld", "any"] = "delivered"


class SimulateCycleResponse(CamelModel):
    """What the cycle actually did, including when it did nothing."""

    mode: Literal["full_loop", "forced_action"]
    session_id: str
    cycle_number: int
    #: `GATE_*` constant, or None on the forced path where no gate ran.
    gate_reason: str | None = None
    should_adapt: bool = False
    ladder_rung: int | None = None
    action_type: str | None = None
    adaptation_id: str | None = None
    text: str | None = None
    variant: str | None = None
    #: True when the text came from the language model, False when a rule fallback produced it.
    generated: bool | None = None
    fallback: bool | None = None
    fallback_reason: str | None = None
    #: Whether the message reached a live socket. False with no browser attached.
    delivered: bool = False
    #: Plain-language caveats: an unreachable action, a missing model, an absent socket. Read
    #: these before concluding anything from a run.
    notes: list[str] = Field(default_factory=list)
    #: The gate settings this cycle was judged against, so a surprising verdict is explicable
    #: without opening the admin page.
    gate_config: dict[str, Any] = Field(default_factory=dict)


class VerifyEmailRequest(CamelModel):
    """Which account to mark verified. Dev only — see the route."""

    email_address: str
