"""Request/response schemas for the runtime system-configuration admin API.

Vocabularies are `Literal`-typed so an out-of-vocabulary value is rejected at the schema boundary
with a 422 before it reaches the service, matching `schemas/study.py`.

The API key is WRITE-ONLY by construction: `LlmKeyRequest` accepts one, and no response model in
this file has a field capable of carrying it back. `LlmKeyStatus` exposes only the last four
characters and a timestamp, which is enough to confirm WHICH key is installed and not enough to
use it anywhere.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.base import CamelModel

ForcedModeLiteral = Literal["auto", "facial_only", "behavioral_only", "multimodal"]


class ConfigValues(CamelModel):
    """The effective configuration — defaults with any admin overrides applied."""

    withhold_rate: float
    max_per_session: int
    min_confidence: float
    min_confidence_geometry: float
    min_confidence_behavioral: float
    min_consecutive: int
    cooldown_cycles: int
    adapt_states: list[str]
    decisive_sources: list[str]
    fusion_drives_decision: bool
    forced_mode: str


class LlmKeyStatus(CamelModel):
    """What can safely be said about a stored key."""

    configured: bool
    #: Last four characters only. Never the key.
    hint: str | None = None
    updated_at: datetime | None = None
    #: False when no encryption secret is available, so the UI can explain why rotation is off
    #: rather than offering a control that will fail.
    can_rotate: bool = True


class ConfigResponse(CamelModel):
    version: int
    locked: bool
    values: ConfigValues
    #: Which keys are explicit overrides rather than environment defaults. The settings page shows
    #: "default (0.70)" versus "overridden to 0.70" — a real distinction when reporting a study's
    #: configuration, and invisible from the values alone.
    overridden: list[str]
    llm_key: LlmKeyStatus


class ConfigPatchRequest(CamelModel):
    """A partial update. Every field is optional; omitted fields are left alone.

    A field explicitly set to `null` CLEARS the override and returns that setting to its
    environment default — which is not the same as setting it to the default's current value,
    because the default may change later.
    """

    withhold_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    max_per_session: int | None = Field(default=None, ge=0, le=100)
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    min_confidence_geometry: float | None = Field(default=None, ge=0.0, le=1.0)
    min_confidence_behavioral: float | None = Field(default=None, ge=0.0, le=1.0)
    min_consecutive: int | None = Field(default=None, ge=1, le=20)
    cooldown_cycles: int | None = Field(default=None, ge=0, le=100)
    adapt_states: list[str] | None = None
    decisive_sources: list[str] | None = None
    fusion_drives_decision: bool | None = None
    forced_mode: ForcedModeLiteral | None = None

    def changes(self, provided: set[str]) -> dict[str, Any]:
        """Only the fields the caller actually sent, camelCased for the service.

        Uses the caller-supplied field set rather than "is not None", so an explicit `null`
        (clear the override) is distinguishable from an omitted field (leave it alone).
        """
        alias = {
            "withhold_rate": "withholdRate",
            "max_per_session": "maxPerSession",
            "min_confidence": "minConfidence",
            "min_confidence_geometry": "minConfidenceGeometry",
            "min_confidence_behavioral": "minConfidenceBehavioral",
            "min_consecutive": "minConsecutive",
            "cooldown_cycles": "cooldownCycles",
            "adapt_states": "adaptStates",
            "decisive_sources": "decisiveSources",
            "fusion_drives_decision": "fusionDrivesDecision",
            "forced_mode": "forcedMode",
        }
        return {alias[f]: getattr(self, f) for f in provided if f in alias}


class LockRequest(CamelModel):
    locked: bool


class LlmKeyRequest(CamelModel):
    #: Write-only. Never echoed by any response model in this module.
    api_key: str = Field(min_length=8, max_length=512)
