"""Seed pre-registered designer and admin accounts. Idempotent."""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import async_session
from app.models.user import Role, User


def _get_seed_accounts() -> list[dict]:
    return [
        {
            "email_address": "learner@affectlearn.io",
            "password": settings.SEED_LEARNER_PASSWORD,
            "first_name": "Demo",
            "last_name": "Learner",
            "role": Role.learner,
        },
        {
            "email_address": "designer@affectlearn.io",
            "password": settings.SEED_DESIGNER_PASSWORD,
            "first_name": "Course",
            "last_name": "Designer",
            "role": Role.course_designer,
        },
        {
            "email_address": "admin@affectlearn.io",
            "password": settings.SEED_ADMIN_PASSWORD,
            "first_name": "Platform",
            "last_name": "Admin",
            "role": Role.admin,
        },
    ]


def get_dev_credentials() -> list[dict]:
    """Return seed credentials (with plaintext password) for development surfaces.

    Never call this from a code path that runs in production — guard with the
    EXPOSE_DEV_CREDENTIALS flag in `settings`.
    """
    return [
        {
            "role": acct["role"].value,
            "email_address": acct["email_address"],
            "password": acct["password"],
            "first_name": acct["first_name"],
            "last_name": acct["last_name"],
        }
        for acct in _get_seed_accounts()
    ]


async def seed_accounts(db: AsyncSession) -> list[str]:
    """Create pre-registered accounts if they don't already exist. Returns list of created emails."""
    created = []
    for acct in _get_seed_accounts():
        result = await db.execute(
            select(User).where(User.email_address == acct["email_address"])
        )
        if result.scalar_one_or_none() is None:
            user = User(
                email_address=acct["email_address"],
                password_hash=hash_password(acct["password"]),
                first_name=acct["first_name"],
                last_name=acct["last_name"],
                role=acct["role"],
                is_active=True,
                email_verified=True,  # seeded accounts are trusted — skip the verification gate
            )
            db.add(user)
            created.append(acct["email_address"])
    await db.commit()
    return created


async def run_seed() -> None:
    async with async_session() as db:
        created = await seed_accounts(db)
        if created:
            print(f"Seeded accounts: {', '.join(created)}")
        else:
            print("All seed accounts already exist — no changes.")


if __name__ == "__main__":
    asyncio.run(run_seed())
