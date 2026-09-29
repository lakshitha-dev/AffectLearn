"""Create pseudonymous pilot accounts and assign them to arms by seeded block randomisation.

WHAT IT DOES
    * creates learner accounts P001..PNNN with an e-mail of `p001@pilot.invalid` and first name
      "P001" -- no real names or e-mail addresses ever enter the database. `.invalid` is reserved
      (RFC 2606), so nothing can ever be sent to one;
    * marks them e-mail-verified (no mail is sent) and not demo;
    * assigns each to `control` or `adaptive` from a pre-generated allocation: blocks of `--block`
      (default 4) with equal arms per block, shuffled by a seeded RNG. The same seed always gives the
      same list, so the allocation is auditable and was fixed before anyone was enrolled;
    * optionally sets the study phase to `phase_b` and locks the assignments;
    * writes code, login e-mail, one-time password and arm to `--out` (CSV). That file is the only
      place the passwords exist. Keep it off the repository, encrypted, and delete it after the
      pilot. The link from code to a person's name is kept on paper, never here.

Idempotent: an existing account for a code is left as it is (and reported), so re-running with a
larger `--count` only adds the new codes.

Usage (inside the api container):
    python -m scripts.create_pilot_participants --count 32 --seed 20261001 \
        --out /app/pilot_accounts.csv --phase-b --lock
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import random
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import async_session
from app.models.user import Role, User
from app.services import study_service
from app.services.consent import CURRENT_CONSENT_VERSION

ARMS = ("control", "adaptive")


def allocation(count: int, seed: int, block: int) -> list[str]:
    """The arm for each participant in enrolment order: equal arms within every block."""
    if block < 2 or block % len(ARMS):
        raise ValueError(f"block must be a positive multiple of {len(ARMS)}")
    rng = random.Random(seed)
    out: list[str] = []
    while len(out) < count:
        chunk = [arm for arm in ARMS for _ in range(block // len(ARMS))]
        rng.shuffle(chunk)
        out.extend(chunk)
    return out[:count]


def code_for(n: int, prefix: str = "P") -> str:
    return f"{prefix}{n:03d}"


READINESS_EMAIL = "readiness@pilot.invalid"


async def create_readiness_account(db, out: Path) -> dict | None:
    """The account the pre-session readiness check signs in as.

    Flagged `is_demo`, so every research surface and `export_pilot` exclude it; already consented
    (all scopes, camera on) and on the adaptive arm, so one run exercises every capture path.
    Returns the credentials row, or None if it already exists.
    """
    existing = (await db.execute(
        select(User).where(User.email_address == READINESS_EMAIL)
    )).scalar_one_or_none()
    if existing is not None:
        print("READY: exists, left unchanged")
        return None
    password = secrets.token_urlsafe(12)
    user = User(
        email_address=READINESS_EMAIL, password_hash=hash_password(password),
        first_name="READY", last_name="Check", role=Role.learner,
        email_verified=True, is_demo=True,
        consent_given_at=datetime.now(timezone.utc), consent_version=CURRENT_CONSENT_VERSION,
        consent_scopes={"behavioural": True, "raw_interaction": True}, webcam_enabled=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await study_service.assign_group(db, user.id, "adaptive")
    row = {"code": "READY", "email": READINESS_EMAIL, "password": password, "arm": "adaptive"}
    _append(out, [row])
    print(f"READY: created -- credentials appended to {out}")
    return row


def _append(out: Path, rows: list[dict]) -> None:
    new_file = not out.exists()
    with out.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["code", "email", "password", "arm"])
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


async def create(db, count: int, seed: int, block: int, out: Path, start: int = 1,
                 prefix: str = "P", phase_b: bool = False, lock: bool = False) -> list[dict]:
    """Create the accounts in `db`. Returns the rows written to `out` (new accounts only)."""
    arms = allocation(start - 1 + count, seed, block)[start - 1:]
    rows: list[dict] = []
    for offset, arm in enumerate(arms):
        code = code_for(start + offset, prefix)
        email = f"{code.lower()}@pilot.invalid"
        existing = (await db.execute(
            select(User).where(User.email_address == email)
        )).scalar_one_or_none()
        if existing is not None:
            print(f"{code}: exists, left unchanged")
            continue
        password = secrets.token_urlsafe(9)
        user = User(
            email_address=email, password_hash=hash_password(password),
            first_name=code, last_name="Pilot", role=Role.learner,
            email_verified=True, is_demo=False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        await study_service.assign_group(db, user.id, arm)
        rows.append({"code": code, "email": email, "password": password, "arm": arm})
        print(f"{code}: created ({arm})")
    if phase_b:
        result = await study_service.set_phase(db, "phase_b")
        print(f"phase: {result['from']} -> {result['to']}")
    if lock:
        print(f"locked {await study_service.lock_assignments(db)} assignment(s)")

    if rows:
        _append(out, rows)
        print(f"wrote {len(rows)} account(s) to {out} -- keep it encrypted, delete after the pilot")
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--count", type=int, default=0)
    parser.add_argument("--seed", type=int, required=True,
                        help="record it in the protocol: it fixes the allocation")
    parser.add_argument("--block", type=int, default=4)
    parser.add_argument("--start", type=int, default=1, help="first participant number")
    parser.add_argument("--prefix", default="P")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--phase-b", action="store_true", help="set the study phase to phase_b")
    parser.add_argument("--lock", action="store_true", help="lock the group assignments")
    parser.add_argument("--readiness", action="store_true",
                        help="also create the demo-flagged account the readiness check uses")
    parser.add_argument("--print-allocation", action="store_true",
                        help="print the allocation list and exit without touching the database")
    args = parser.parse_args(argv)

    if args.print_allocation:
        for n, arm in enumerate(allocation(args.start - 1 + args.count, args.seed, args.block),
                                start=1):
            if n >= args.start:
                print(f"{code_for(n, args.prefix)},{arm}")
        return 0
    async def run() -> None:
        async with async_session() as db:
            if args.readiness:
                await create_readiness_account(db, args.out)
            await create(db, args.count, args.seed, args.block, args.out, args.start,
                         args.prefix, args.phase_b, args.lock)

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
