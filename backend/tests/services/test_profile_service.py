"""Tests for profile logic + cold store (Story 4.5 AC1/AC3)."""

import pytest

from app.services import profile_service as ps


def test_default_profile_shape():
    p = ps.default_profile()
    assert p["affect_state"] is None
    assert p["affect_history"] == []
    assert p["skill_level"] == "intermediate"
    assert p["topic_mastery"] == {} and p["format_preferences"] == {}
    assert p["cycle_count"] == 0


def test_apply_affect_appends_and_caps_history():
    p = ps.default_profile()
    for i in range(25):
        p = ps.apply_affect(p, "engaged", i, now_ms=1000 + i)
    assert len(p["affect_history"]) == 20      # bounded
    assert p["affect_state"] == "engaged"
    assert p["cycle_count"] == 25
    assert p["updated_at"] == 1024


def test_apply_affect_none_keeps_affect_but_stamps_time():
    p = ps.apply_affect(ps.default_profile(), None, 1, now_ms=500)
    assert p["affect_state"] is None
    assert p["affect_history"] == []
    assert p["cycle_count"] == 0
    assert p["updated_at"] == 500


def test_skill_thresholds():
    assert ps.skill_from_preassessment(0.3) == "low"
    assert ps.skill_from_preassessment(0.6) == "intermediate"
    assert ps.skill_from_preassessment(0.9) == "advanced"


@pytest.mark.asyncio
async def test_cold_persist_and_load_roundtrip(db, test_user):
    prof = {**ps.default_profile(), "skill_level": "advanced", "cycle_count": 7}
    await ps.persist_cold(db, test_user.id, prof)
    loaded = await ps.load_cold(db, test_user.id)
    assert loaded["skill_level"] == "advanced"
    assert loaded["cycle_count"] == 7


@pytest.mark.asyncio
async def test_persist_cold_upserts(db, test_user):
    await ps.persist_cold(db, test_user.id, {**ps.default_profile(), "skill_level": "low"})
    await ps.persist_cold(db, test_user.id, {**ps.default_profile(), "skill_level": "advanced"})
    loaded = await ps.load_cold(db, test_user.id)
    assert loaded["skill_level"] == "advanced"   # second write updated, not duplicated


@pytest.mark.asyncio
async def test_init_from_preassessment_defaults_without_attempts(db, test_user):
    prof = await ps.init_from_preassessment(db, test_user.id)
    assert prof["skill_level"] == "intermediate"


@pytest.mark.asyncio
async def test_load_or_init_prefers_cold(db, test_user):
    await ps.persist_cold(db, test_user.id, {**ps.default_profile(), "skill_level": "low"})
    out = await ps.load_or_init(db, test_user.id)
    assert out["skill_level"] == "low"
