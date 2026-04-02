"""Application lifespan management for startup and shutdown events."""

import logging
from contextlib import asynccontextmanager

import sqlalchemy
from fastapi import FastAPI
from sqlmodel import SQLModel

from src.db.operations import async_engine
from src.utils.seed import run_all_seeds

logger = logging.getLogger(__name__)


@asynccontextmanager
async def database():
    """Initialize database tables on startup."""
    logger.info("Creating database tables...")
    async with async_engine.begin() as conn:
        await conn.execute(sqlalchemy.text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("Database tables created successfully")
    yield
    logger.info("Closing database connections...")
    await async_engine.dispose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan with startup and shutdown events."""
    logger.info("Starting application...")
    async with database():
        await run_all_seeds()
        yield
    logger.info("Application shutdown complete")
