"""Database seeding for initial application data.

Provides idempotent seed functions that can be called from:
- App lifespan (automatic on startup)
- CLI: `just seed` (manual re-seed without restarting the API)

Seed functions check for existing data before inserting, so they are
safe to run multiple times.
"""

import logging

from sqlmodel import select

from src.db.models import DBUser
from src.db.operations import managed_session
from src.settings import settings
from src.utils.auth import hash_password

logger = logging.getLogger(__name__)


async def seed_admin() -> None:
    """Seed the initial admin user if one does not already exist."""
    async with managed_session() as session:
        stmt = select(DBUser).where(DBUser.email == settings.SEED_ADMIN_EMAIL)
        result = await session.exec(stmt)
        existing = result.first()

        if existing:
            logger.info("Seed admin user already exists, skipping")
            return

        admin = DBUser(
            email=settings.SEED_ADMIN_EMAIL,
            full_name=settings.SEED_ADMIN_FULL_NAME,
            hashed_password=hash_password(settings.SEED_ADMIN_PASSWORD),
            role="admin",
        )
        session.add(admin)
        await session.flush()
        logger.info("Seed admin user created: %s", settings.SEED_ADMIN_EMAIL)


async def run_all_seeds() -> None:
    """Run all seed functions. Called from app lifespan on startup."""
    await seed_admin()
