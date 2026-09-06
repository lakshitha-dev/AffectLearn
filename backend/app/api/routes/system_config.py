"""Admin API for runtime system configuration.

Every route is admin-guarded and every mutation is recorded in the research record with the actor
who performed it — the only audit trail there is for who changed a threshold and when.

TWO THINGS THIS API REFUSES TO DO

  * Return a stored API key. `PUT /llm-key` accepts one; nothing gives one back. The response
    models in `schemas/system_config.py` have no field capable of carrying it.
  * Change a threshold while the configuration is locked. A 409 is the point: once collection has
    begun, a silent threshold change makes the cycles either side of it incomparable, and the
    dataset would not show that it happened.
"""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.models.user import Role, User
from app.schemas.system_config import (
    ConfigPatchRequest,
    ConfigResponse,
    ConfigValues,
    LlmKeyRequest,
    LlmKeyStatus,
    LockRequest,
)
from app.services import config_service

logger = structlog.get_logger(__name__)
router = APIRouter()


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


async def _response(db: AsyncSession) -> ConfigResponse:
    """Build the full settings view from the live config plus the stored row."""
    config = config_service.get_config()
    row = await config_service._row(db)
    overridden = sorted((row.values or {}).keys()) if row is not None else []

    can_rotate = True
    try:
        config_service._fernet()
    except Exception:
        # No key material, so rotation would fail. Say so, rather than offering a broken control.
        can_rotate = False

    return ConfigResponse(
        version=config.version,
        locked=config.locked,
        values=ConfigValues(
            withhold_rate=config.withhold_rate,
            max_per_session=config.max_per_session,
            min_confidence=config.min_confidence,
            min_confidence_geometry=config.min_confidence_geometry,
            min_confidence_behavioral=config.min_confidence_behavioral,
            min_consecutive=config.min_consecutive,
            cooldown_cycles=config.cooldown_cycles,
            adapt_states=list(config.adapt_states),
            decisive_sources=list(config.decisive_sources),
            fusion_drives_decision=config.fusion_drives_decision,
            forced_mode=config.forced_mode,
        ),
        overridden=overridden,
        llm_key=LlmKeyStatus(
            configured=bool(row is not None and row.llm_api_key_encrypted),
            hint=row.llm_api_key_hint if row is not None else None,
            updated_at=row.llm_api_key_updated_at if row is not None else None,
            can_rotate=can_rotate,
        ),
    )


@router.get("/config", response_model=ConfigResponse)
async def get_config(
    _: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """The effective configuration, which settings are overridden, and the key's status."""
    return await _response(db)


@router.patch("/config", response_model=ConfigResponse)
async def patch_config(
    body: ConfigPatchRequest,
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Apply overrides. 409 while locked.

    `exclude_unset` is what makes an explicit `null` (clear the override) distinguishable from an
    omitted field (leave it alone) — without it every unsent field would read as a request to
    reset it to the default.
    """
    provided = set(body.model_dump(exclude_unset=True).keys())
    changes = body.changes(provided)
    if not changes:
        return await _response(db)

    try:
        await config_service.set_values(db, changes, actor_id=current_user.id)
    except config_service.ConfigLockedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_error(
                "CONFIG_LOCKED",
                "Configuration is locked for data collection. Unlock it first — and note that "
                "changing a threshold mid-study makes the cycles either side incomparable.",
            ),
        )
    except config_service.InvalidConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error("INVALID_CONFIG", str(exc)),
        )
    return await _response(db)


@router.post("/config/lock", response_model=ConfigResponse)
async def set_lock(
    body: LockRequest,
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Lock or unlock. Both directions are recorded; an unlock during collection matters most."""
    await config_service.set_locked(db, body.locked, actor_id=current_user.id)
    return await _response(db)


@router.put("/config/llm-key", response_model=LlmKeyStatus)
async def rotate_llm_key(
    body: LlmKeyRequest,
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Replace the LLM API key. Takes effect immediately; the key is never returned.

    Deliberately NOT blocked by the lock: the lock protects the study's THRESHOLDS, and a key
    rotation changes no measurement. Blocking it would mean a compromised key could not be
    replaced without first unlocking the study, which is the wrong trade.
    """
    try:
        result = await config_service.set_llm_api_key(db, body.api_key, actor_id=current_user.id)
    except config_service.EncryptionUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error(
                "ENCRYPTION_UNAVAILABLE",
                "No encryption secret is configured, so a key cannot be stored safely. "
                "Set CONFIG_SECRET_KEY and try again.",
            ),
        )
    except config_service.InvalidConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error("INVALID_API_KEY", str(exc)),
        )

    return LlmKeyStatus(
        configured=True, hint=result["hint"], updated_at=result["updatedAt"], can_rotate=True
    )
