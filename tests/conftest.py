"""Pytest configuration and fixtures."""

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from src.db.models import DBUser
from src.db.operations import ManagedAsyncSession, get_db_session
from src.main import app
from src.routes.v1.authors.service import AuthorService
from src.routes.v1.books.service import BookService
from src.routes.v1.orders.service import OrderService
from src.routes.v1.users.service import UserService
from src.settings import settings
from src.utils.auth import authenticate_user, hash_password


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    # Create test engine - matching db/operations.py pattern
    async_engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_POOL_SIZE_OVERFLOW,
        echo=False,
    )

    # Create tables
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # Create session factory - matching db/operations.py pattern
    AsyncSessionLocal = async_sessionmaker(async_engine, class_=ManagedAsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

    # Cleanup: drop all tables
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

    await async_engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    def get_session_override() -> AsyncSession:
        return db_session

    app.dependency_overrides[get_db_session] = get_session_override

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def user_service(db_session: AsyncSession) -> UserService:
    return UserService(db_session=db_session)


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> DBUser:
    user = DBUser(
        email=f"test_{uuid.uuid4()}@example.com",
        full_name="Test User",
        hashed_password=hash_password("testpassword123"),
        role="admin",
        is_active=True,
    )
    await db_session.create(user)
    return user


@pytest_asyncio.fixture
async def test_customer(db_session: AsyncSession) -> DBUser:
    user = DBUser(
        email=f"customer_{uuid.uuid4()}@example.com",
        full_name="Test Customer",
        hashed_password=hash_password("customerpassword123"),
        role="customer",
        is_active=True,
    )
    await db_session.create(user)
    return user


@pytest_asyncio.fixture
async def authenticated_client(client: AsyncClient, test_user: DBUser) -> AsyncClient:
    """Client authenticated as an admin user.

    Does NOT override require_admin — lets FastAPI's DI chain resolve it
    naturally through authenticate_user, so the real role check runs.
    """

    async def mock_authenticate_user() -> DBUser:
        return test_user

    app.dependency_overrides[authenticate_user] = mock_authenticate_user
    return client


@pytest_asyncio.fixture
async def customer_client(client: AsyncClient, test_customer: DBUser) -> AsyncClient:
    """Client authenticated as a customer user.

    require_admin is NOT overridden, so admin-only routes will reject
    this user with 403 via the real role check.
    """

    async def mock_authenticate_user() -> DBUser:
        return test_customer

    app.dependency_overrides[authenticate_user] = mock_authenticate_user
    return client


@pytest.fixture
def user_signup_data() -> dict:
    return {
        "email": f"user_{uuid.uuid4()}@example.com",
        "full_name": "New User",
        "password": "securepassword123",
    }


@pytest.fixture
def user_login_data() -> dict:
    return {
        "email": "test@example.com",
        "password": "testpassword123",
    }


@pytest_asyncio.fixture
async def author_service(db_session: AsyncSession) -> AuthorService:
    return AuthorService(db_session=db_session)


@pytest_asyncio.fixture
async def book_service(db_session: AsyncSession) -> BookService:
    return BookService(db_session=db_session)


@pytest_asyncio.fixture
async def order_service(db_session: AsyncSession) -> OrderService:
    return OrderService(db_session=db_session)
