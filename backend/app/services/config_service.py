"""Runtime-editable system configuration: the single accessor everything reads through.

WHAT THIS REPLACES

The gate's thresholds were module-level constants in `agents/edges.py`, read from the environment
at import time. Changing one meant editing Azure app settings and restarting the process. This
service puts the same values behind an accessor backed by a singleton table, so an admin can change
them from the settings page and the next detection cycle uses the new value.

ONLY OVERRIDES ARE STORED

`SystemConfig.values` holds only keys an admin has explicitly set. Everything else falls through to
the env/code defaults in `edges.py`, which means an empty row behaves exactly as the deployment did
before this table existed — a fresh deploy changes nothing until someone deliberately changes
something. It also lets the settings page distinguish "0.70, the default" from "0.70, chosen",
which is a real distinction when reporting a study's configuration.

WHY AN IN-PROCESS CACHE IS SAFE HERE

`startup.sh` runs uvicorn with `--workers 1`, so there is one process holding one cache. The cache
is invalidated on write rather than polled on a TTL, so a change takes effect on the very next
cycle with no database read in the hot path. If the deployment ever moves to multiple workers this
assumption breaks and the cache must become TTL-based — hence `_CACHE_IS_SINGLE_WORKER_ONLY`.

VERSION STAMPING IS NOT OPTIONAL

`version` increments on EVERY mutation and is stamped onto every research event by
`research_logger.emit`. Without it, a threshold changed halfway through data collection would leave
no trace: the cycles before and after would not be comparable, an analysis would pool them anyway,
and the result would be wrong in a way nobody could detect afterwards. `get_version()` is therefore
a synchronous read of the cache — the logger cannot await, and an event without a version would
defeat the purpose.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import edges
from app.core.config import settings
from app.models.system_config import SystemConfig

logger = structlog.get_logger(__name__)

#: Documented assumption, checked nowhere at runtime because there is nothing sensible to do about
#: it in-process. See the module docstring.
_CACHE_IS_SINGLE_WORKER_ONLY = True


class ConfigLockedError(RuntimeError):
    """A mutation was attempted while the configuration is locked for data collection."""


class InvalidConfigError(ValueError):
    """A supplied value is outside its permitted range or vocabulary."""


class EncryptionUnavailableError(RuntimeError):
    """No key material is available, so a secret cannot be stored safely."""


@dataclass(frozen=True)
class GateConfig:
    """The effective configuration. Frozen so a caller cannot mutate shared state by accident."""

    version: int
    locked: bool

    # Trial
    withhold_rate: float
    max_per_session: int

    # Gate thresholds
    min_confidence: float
    min_confidence_geometry: float
    min_confidence_behavioral: float
    min_consecutive: int
    cooldown_cycles: int
    adapt_states: tuple[str, ...]

    # Detection channels
    decisive_sources: tuple[str, ...]
    fusion_drives_decision: bool
    forced_mode: str

    def min_confidence_for(self, affect_source: str | None) -> float:
        """This config's floor for a channel. Mirrors `edges.min_confidence_for`."""
        if affect_source == edges.AFFECT_SOURCE_FACIAL_GEOMETRY:
            return self.min_confidence_geometry
        if affect_source == edges.AFFECT_SOURCE_BEHAVIORAL:
            return self.min_confidence_behavioral
        if affect_source in edges._CHANNEL_MIN_CONFIDENCE:
            return edges._CHANNEL_MIN_CONFIDENCE[affect_source]
        return self.min_confidence


#: Field name -> (type, validator). The validator returns the coerced value or raises.
def _pct(name: str, v: Any) -> float:
    f = float(v)
    if not 0.0 <= f <= 1.0:
        raise InvalidConfigError(f"{name} must be between 0 and 1, got {f}")
    return f


def _positive_int(name: str, v: Any) -> int:
    i = int(v)
    if i < 0:
        raise InvalidConfigError(f"{name} must be zero or greater, got {i}")
    return i


def _states(name: str, v: Any) -> tuple[str, ...]:
    items = tuple(s.strip() for s in (v if isinstance(v, (list, tuple)) else str(v).split(","))
                  if str(s).strip())
    from app.agents.state import AFFECT_STATES

    unknown = [s for s in items if s not in AFFECT_STATES]
    if unknown:
        raise InvalidConfigError(f"{name}: unknown affect states {unknown}")
    return items


def _sources(name: str, v: Any) -> tuple[str, ...]:
    items = tuple(s.strip() for s in (v if isinstance(v, (list, tuple)) else str(v).split(","))
                  if str(s).strip())
    unknown = [s for s in items if s not in edges._KNOWN_AFFECT_SOURCES]
    if unknown:
        raise InvalidConfigError(f"{name}: unknown affect sources {unknown}")
    return items


def _mode(name: str, v: Any) -> str:
    from app.agents.fusion import _VALID_MODES

    s = str(v).strip().lower()
    if s not in _VALID_MODES:
        raise InvalidConfigError(f"{name} must be one of {sorted(_VALID_MODES)}, got {s!r}")
    return s


#: The editable surface. Anything not here cannot be set through the API, which keeps the
#: settings page from becoming a back door into arbitrary process configuration.
EDITABLE: dict[str, Any] = {
    "withholdRate": _pct,
    "maxPerSession": _positive_int,
    "minConfidence": _pct,
    "minConfidenceGeometry": _pct,
    "minConfidenceBehavioral": _pct,
    "minConsecutive": _positive_int,
    "cooldownCycles": _positive_int,
    "adaptStates": _states,
    "decisiveSources": _sources,
    "fusionDrivesDecision": lambda n, v: bool(v),
    "forcedMode": _mode,
}

_cache: GateConfig | None = None


def _defaults() -> dict[str, Any]:
    """The values that apply with no overrides — i.e. exactly today's deployed behaviour."""
    from app.agents.fusion import forced_mode
    from app.agents.nodes.affect_detection import fusion_drives_decision

    return {
        "withholdRate": edges.ADAPT_WITHHOLD_RATE,
        "maxPerSession": edges.ADAPT_MAX_PER_SESSION,
        "minConfidence": edges.ADAPT_MIN_CONFIDENCE,
        "minConfidenceGeometry": edges.min_confidence_for(edges.AFFECT_SOURCE_FACIAL_GEOMETRY),
        "minConfidenceBehavioral": edges.min_confidence_for(edges.AFFECT_SOURCE_BEHAVIORAL),
        "minConsecutive": edges.ADAPT_MIN_CONSECUTIVE,
        "cooldownCycles": edges.ADAPT_COOLDOWN_CYCLES,
        "adaptStates": tuple(edges.ADAPT_STATES),
        "decisiveSources": tuple(edges.DECISIVE_AFFECT_SOURCES),
        "fusionDrivesDecision": bool(fusion_drives_decision()),
        "forcedMode": forced_mode(),
    }


def _build(values: dict[str, Any], version: int, locked: bool) -> GateConfig:
    """Overlay stored overrides on the defaults. Unknown or invalid stored keys are IGNORED.

    Deliberately forgiving on read: a value that fails validation now (because the vocabulary
    changed under it, say) must not take the whole gate down — the system falls back to the
    default for that one key and logs it, rather than refusing to serve any learner.
    """
    merged = _defaults()
    for key, raw in (values or {}).items():
        validator = EDITABLE.get(key)
        if validator is None:
            logger.warning("config_unknown_key_ignored", key=key)
            continue
        try:
            merged[key] = validator(key, raw)
        except Exception as exc:
            logger.warning("config_invalid_value_ignored", key=key, error=str(exc))

    return GateConfig(
        version=version,
        locked=locked,
        withhold_rate=merged["withholdRate"],
        max_per_session=merged["maxPerSession"],
        min_confidence=merged["minConfidence"],
        min_confidence_geometry=merged["minConfidenceGeometry"],
        min_confidence_behavioral=merged["minConfidenceBehavioral"],
        min_consecutive=merged["minConsecutive"],
        cooldown_cycles=merged["cooldownCycles"],
        adapt_states=tuple(merged["adaptStates"]),
        decisive_sources=tuple(merged["decisiveSources"]),
        fusion_drives_decision=bool(merged["fusionDrivesDecision"]),
        forced_mode=merged["forcedMode"],
    )


def get_config() -> GateConfig:
    """The effective configuration, from cache. Synchronous — the hot path must not hit the DB.

    Before `load()` has run (early startup, or any test that never primed it) this returns the
    pure-default configuration, which is the pre-existing deployed behaviour.
    """
    global _cache
    if _cache is None:
        _cache = _build({}, version=1, locked=False)
    return _cache


def get_version() -> int:
    """The version to stamp on a research event. Synchronous: `research_logger` cannot await."""
    return get_config().version


def _reset() -> None:
    """Drop the cache. Used by tests and after any write."""
    global _cache
    _cache = None


async def _row(db: AsyncSession) -> SystemConfig | None:
    """The singleton row by ordered first-fetch, mirroring `study_service._get_phase_row`."""
    result = await db.execute(
        select(SystemConfig).order_by(SystemConfig.created_at.asc()).limit(1)
    )
    return result.scalar_one_or_none()


async def load(db: AsyncSession) -> GateConfig:
    """Read the row into the cache. Called at startup and after every write."""
    global _cache
    try:
        row = await _row(db)
    except Exception as exc:
        # A missing table (pre-migration) must not stop the app booting; defaults are correct.
        logger.warning("config_load_failed_using_defaults", error=f"{type(exc).__name__}: {exc}")
        _cache = _build({}, version=1, locked=False)
        return _cache

    if row is None:
        _cache = _build({}, version=1, locked=False)
    else:
        _cache = _build(row.values or {}, version=int(row.version or 1),
                        locked=row.locked_at is not None)
    return _cache


async def _get_or_create(db: AsyncSession) -> SystemConfig:
    row = await _row(db)
    if row is None:
        row = SystemConfig(version=1, values={})
        db.add(row)
        await db.flush()
    return row


async def set_values(
    db: AsyncSession, changes: dict[str, Any], *, actor_id: Any = None
) -> GateConfig:
    """Apply overrides, bump the version, record who did it.

    Refuses while locked. A key set to `None` CLEARS the override, returning that setting to its
    environment default — which is different from setting it to the default's current value,
    because the default may later change.
    """
    row = await _get_or_create(db)
    if row.locked_at is not None:
        raise ConfigLockedError("configuration is locked for data collection")

    validated: dict[str, Any] = {}
    for key, raw in changes.items():
        validator = EDITABLE.get(key)
        if validator is None:
            raise InvalidConfigError(f"{key} is not an editable setting")
        if raw is None:
            validated[key] = None       # sentinel: clear the override
        else:
            coerced = validator(key, raw)
            validated[key] = list(coerced) if isinstance(coerced, tuple) else coerced

    before = dict(row.values or {})
    after = dict(before)
    for key, value in validated.items():
        if value is None:
            after.pop(key, None)
        else:
            after[key] = value

    if after == before:
        # A no-op set is not a change: bumping the version would fragment the dataset on a
        # boundary where nothing actually differs.
        return get_config()

    row.values = after
    row.version = int(row.version or 1) + 1
    await db.commit()
    await db.refresh(row)

    config = await load(db)
    await _emit_change(
        "config_changed",
        version=row.version,
        actor_id=actor_id,
        payload={"changed": sorted(set(after) ^ set(before) | {
            k for k in after if before.get(k) != after.get(k)
        }), "from": before, "to": after},
    )
    return config


async def set_locked(db: AsyncSession, locked: bool, *, actor_id: Any = None) -> GateConfig:
    """Lock or unlock. Both directions are recorded — an unlock during collection matters most."""
    row = await _get_or_create(db)
    already = row.locked_at is not None
    if already == locked:
        return get_config()

    row.locked_at = datetime.now(timezone.utc) if locked else None
    row.version = int(row.version or 1) + 1
    await db.commit()
    await db.refresh(row)

    config = await load(db)
    await _emit_change(
        "config_locked" if locked else "config_unlocked",
        version=row.version,
        actor_id=actor_id,
        payload={"locked_at": row.locked_at.isoformat() if row.locked_at else None},
    )
    return config


# ── the LLM API key ───────────────────────────────────────────────────────────────────

def _fernet():
    """Fernet built from a dedicated secret, falling back to one derived from `JWT_SECRET`.

    The fallback exists so this feature needs no new required environment variable — a deploy that
    has not set `CONFIG_SECRET_KEY` still gets encryption rather than a broken page. The trade is
    that rotating `JWT_SECRET` orphans a stored key; the recovery is to paste the API key again,
    which is mild and self-evident (generation starts failing and the settings page says the key
    cannot be read).

    Raises rather than falling back to plaintext when no secret exists at all.
    """
    from cryptography.fernet import Fernet

    secret = os.getenv("CONFIG_SECRET_KEY") or getattr(settings, "JWT_SECRET", "")
    if not secret:
        raise EncryptionUnavailableError("no CONFIG_SECRET_KEY or JWT_SECRET available")
    # HKDF-style derivation to a valid 32-byte Fernet key, so any secret string works.
    digest = hashlib.sha256(f"affectlearn.config.v1:{secret}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


async def set_llm_api_key(db: AsyncSession, key: str, *, actor_id: Any = None) -> dict[str, Any]:
    """Store an encrypted API key and drop the cached LLM client so it takes effect immediately.

    The key is never returned, never logged, and never written anywhere but the encrypted column.
    Only the last four characters are kept in the clear, so an admin can confirm WHICH key is
    installed without the system being able to disclose it.
    """
    key = (key or "").strip()
    if len(key) < 8:
        raise InvalidConfigError("that does not look like an API key")

    token = _fernet().encrypt(key.encode("utf-8")).decode("ascii")

    row = await _get_or_create(db)
    row.llm_api_key_encrypted = token
    row.llm_api_key_hint = key[-4:]
    row.llm_api_key_updated_at = datetime.now(timezone.utc)
    row.version = int(row.version or 1) + 1
    await db.commit()
    await db.refresh(row)

    await load(db)
    _apply_llm_key(key)
    await _emit_change(
        "config_llm_key_rotated",
        version=row.version,
        actor_id=actor_id,
        # The hint only. Never the key, not even truncated beyond four characters.
        payload={"hint": row.llm_api_key_hint},
    )
    return {"hint": row.llm_api_key_hint, "updatedAt": row.llm_api_key_updated_at}


def _apply_llm_key(key: str) -> None:
    """Push a key into the running process and reset the cached chat client.

    `llm.get_chat_client` caches its client in a module global, so a new key has no effect until
    that cache is dropped — a rotation that silently kept using the old key would look like it
    worked right up until the old key was revoked.
    """
    from app.agents import llm

    os.environ["VLLM_API_KEY"] = key
    try:
        settings.VLLM_API_KEY = key    # the client reads from `settings`, not the environment
    except Exception:
        pass
    llm._reset()


async def apply_stored_llm_key(db: AsyncSession) -> bool:
    """At startup, decrypt the stored key (if any) into the running process.

    Returns whether a key was applied. A decryption failure is logged and ignored: the deployment
    keeps whatever key its environment supplies, which is the pre-existing behaviour.
    """
    try:
        row = await _row(db)
    except Exception:
        return False
    if row is None or not row.llm_api_key_encrypted:
        return False
    try:
        key = _fernet().decrypt(row.llm_api_key_encrypted.encode("ascii")).decode("utf-8")
    except Exception as exc:
        logger.warning("config_llm_key_undecryptable", error=type(exc).__name__)
        return False
    _apply_llm_key(key)
    return True


async def _emit_change(event_type: str, *, version: int, actor_id: Any, payload: dict) -> None:
    """Record a configuration change in the research record.

    Mirrors `study_service.set_phase`, the existing precedent for attributing a config change to a
    person. This is the only audit trail for who changed a threshold and when.
    """
    from app.services.research_logger import emit as emit_research_event

    await emit_research_event({
        "event_type": event_type,
        "learner_id": None,
        "session_id": None,
        "cycle_number": 0,
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        "phase": None,
        "group": None,
        "payload": {**payload, "version": version,
                    "actor_id": str(actor_id) if actor_id is not None else None},
    })
