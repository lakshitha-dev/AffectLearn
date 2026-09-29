"""The pilot account script: pseudonymous accounts, a fixed seeded allocation, balanced blocks."""

import csv
from collections import Counter

import pytest
from sqlalchemy import select

from app.models.study_group import StudyGroup
from app.models.user import User
from app.services import study_service
from scripts.create_pilot_participants import allocation, code_for, create


def test_allocation_is_balanced_within_every_block():
    arms = allocation(32, seed=20261001, block=4)
    for i in range(0, 32, 4):
        assert Counter(arms[i:i + 4]) == {"control": 2, "adaptive": 2}


def test_allocation_is_fixed_by_the_seed():
    assert allocation(20, seed=7, block=4) == allocation(20, seed=7, block=4)
    assert allocation(20, seed=7, block=4) != allocation(20, seed=8, block=4)


def test_allocation_refuses_an_unbalanced_block():
    with pytest.raises(ValueError):
        allocation(8, seed=1, block=3)


def test_codes_are_zero_padded():
    assert code_for(7) == "P007"


@pytest.mark.asyncio
async def test_creates_pseudonymous_accounts_and_assigns_arms(db, tmp_path):
    out = tmp_path / "accounts.csv"
    rows = await create(db, 8, seed=99, block=4, out=out, phase_b=True, lock=True)

    assert [r["code"] for r in rows] == [f"P00{i}" for i in range(1, 9)]
    users = (await db.execute(select(User).order_by(User.email_address))).scalars().all()
    assert all(u.email_address.endswith("@pilot.invalid") for u in users)
    assert all(u.first_name.startswith("P0") and u.last_name == "Pilot" for u in users)
    assert all(u.email_verified and not u.is_demo for u in users)

    groups = (await db.execute(select(StudyGroup))).scalars().all()
    assert Counter(g.group for g in groups) == {"control": 4, "adaptive": 4}
    assert all(g.locked_at is not None for g in groups)
    assert await study_service.get_phase(db) == "phase_b"

    with out.open(encoding="utf-8") as fh:
        written = list(csv.DictReader(fh))
    assert [w["arm"] for w in written] == allocation(8, seed=99, block=4)


@pytest.mark.asyncio
async def test_rerunning_only_adds_new_codes(db, tmp_path):
    out = tmp_path / "accounts.csv"
    await create(db, 4, seed=5, block=4, out=out)
    more = await create(db, 8, seed=5, block=4, out=out)
    assert [r["code"] for r in more] == ["P005", "P006", "P007", "P008"]
    assert [r["arm"] for r in more] == allocation(8, seed=5, block=4)[4:]


@pytest.mark.asyncio
async def test_readiness_account_is_demo_consented_and_adaptive(db, tmp_path):
    from scripts.create_pilot_participants import READINESS_EMAIL, create_readiness_account

    out = tmp_path / "accounts.csv"
    row = await create_readiness_account(db, out)
    assert row["code"] == "READY"
    user = (await db.execute(select(User).where(User.email_address == READINESS_EMAIL))).scalar_one()
    assert user.is_demo and user.webcam_enabled and user.consent_given_at is not None
    assert user.consent_scopes == {"behavioural": True, "raw_interaction": True}
    assert await study_service.get_group(db, user.id) == "adaptive"
    assert await create_readiness_account(db, out) is None      # idempotent
