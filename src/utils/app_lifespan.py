"""Application lifespan management for startup and shutdown events."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import SQLModel, select

from src.db.models import DBUser
from src.db.operations import async_engine, managed_session
from src.settings import settings
from src.utils.auth import hash_password

logger = logging.getLogger(__name__)


@asynccontextmanager
async def database():
    """Initialize database tables on startup."""
    logger.info("Creating database tables...")
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("Database tables created successfully")
    yield
    logger.info("Closing database connections...")
    await async_engine.dispose()


async def seed_admin():
    """Seed the initial admin user if one does not already exist.

    Idempotent: checks by email before inserting, safe to run on every startup.
    """
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan with startup and shutdown events."""
    logger.info("Starting application...")
    async with database():
        await seed_admin()
        yield
    logger.info("Application shutdown complete")
