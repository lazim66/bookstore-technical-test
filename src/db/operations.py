from contextlib import asynccontextmanager
from typing import AsyncGenerator, TypeVar

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from src.settings import settings

T = TypeVar("T", bound=SQLModel)


class ManagedAsyncSession(AsyncSession):
    """AsyncSession with convenience methods for common operations."""

    async def create(self, instance: T) -> T:
        """Add a new instance to the session and flush to persist and populate server-generated values."""
        self.add(instance)
        await self.flush()
        return instance

    async def update(self, instance: T) -> T:
        """Flush pending changes and refresh to get server-generated values."""
        await self.flush()
        await self.refresh(instance)
        return instance


# SQLAlchemy engine with custom pool settings
async_engine = create_async_engine(
    settings.DATABASE_URL, pool_size=settings.DATABASE_POOL_SIZE, max_overflow=settings.DATABASE_POOL_SIZE_OVERFLOW
)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=ManagedAsyncSession, expire_on_commit=False)


@asynccontextmanager
async def managed_session():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_session() -> AsyncGenerator[ManagedAsyncSession, None]:
    async with managed_session() as session:
        yield session
