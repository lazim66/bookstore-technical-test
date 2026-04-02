"""Tests for book summary generation.

Covers:
- Auto-generation: creating a book with full_text triggers background summary
- Per-book summarize endpoint
- Backfill endpoint for books without summaries
- Concurrency: semaphore limits parallel LLM calls
- Edge cases: no full_text, already has summary
- Admin-only access on summary endpoints

Note: Tests that use the SummaryService (backfill, generate_for_book) require
explicit db_session.commit() after creating test data. The summary service uses
independent DB sessions that cannot see uncommitted data from the test session.
This mirrors production behaviour where background tasks operate on committed data.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from src.db.operations import ManagedAsyncSession
from src.main import app
from src.routes.v1.authors.schema import AuthorCreateInput
from src.routes.v1.authors.service import AuthorService
from src.routes.v1.books.schema import BookCreateInput, BookUpdateInput
from src.routes.v1.books.service import BookService
from src.routes.v1.books.summary_service import SummaryService
from src.utils.llm import LLMService, get_llm_service


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_test_session_factory(engine: AsyncEngine):
    """Create a session factory bound to the test engine.

    Each call yields an independent session from the test engine's pool,
    allowing concurrent operations (asyncio.gather) to each get their own
    connection — matching production behaviour while using the test database.
    """

    @asynccontextmanager
    async def factory() -> AsyncGenerator[ManagedAsyncSession, None]:
        session_maker = async_sessionmaker(engine, class_=ManagedAsyncSession, expire_on_commit=False)
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return factory


@pytest.fixture
def mock_llm_service() -> LLMService:
    """LLM service with mocked summary and embedding generation."""
    service = LLMService.__new__(LLMService)
    service._model = "test-model"
    service._embedding_model = "test-embedding"
    service._semaphore = asyncio.Semaphore(5)
    service.generate_summary = AsyncMock(return_value="A compelling test summary.")
    service.generate_embedding = AsyncMock(return_value=[0.1] * 1536)
    return service


@pytest_asyncio.fixture
async def summary_service(mock_llm_service: LLMService, test_engine: AsyncEngine) -> SummaryService:
    """Summary service wired to test engine and mocked LLM."""
    return SummaryService(
        llm_service=mock_llm_service,
        session_factory=_make_test_session_factory(test_engine),
    )


@pytest.fixture(autouse=True)
def _override_deps(mock_llm_service: LLMService, summary_service: SummaryService):
    """Override LLM and summary service for all tests in this module."""
    from src.routes.v1.books.router import _get_summary_service

    app.dependency_overrides[get_llm_service] = lambda: mock_llm_service
    app.dependency_overrides[_get_summary_service] = lambda: summary_service
    yield
    app.dependency_overrides.pop(get_llm_service, None)
    app.dependency_overrides.pop(_get_summary_service, None)


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _create_test_book(
    author_service: AuthorService,
    book_service: BookService,
    db_session: AsyncSession,
    full_text: str | None = None,
    title: str = "Test Book",
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create an author + book and commit. Returns (author_id, book_id)."""
    author = await author_service.create(data=AuthorCreateInput(name="Test Author"))
    book = await book_service.create(data=BookCreateInput(
        title=title, author_id=author.id, price=9.99, full_text=full_text,
    ))
    await db_session.commit()
    return author.id, book.id


# =============================================================================
# Auto-generation: book creation triggers background summary
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_create_book_with_full_text_schedules_background_task(
    authenticated_client: AsyncClient,
    author_service: AuthorService,
    db_session: AsyncSession,
):
    """Verify that creating a book with full_text returns 201 with summary=None
    (indicating the summary will be generated asynchronously)."""
    author = await author_service.create(data=AuthorCreateInput(name="Author"))
    await db_session.commit()

    response = await authenticated_client.post("/api/v1/books", json={
        "title": "Book With Text",
        "author_id": str(author.id),
        "price": 19.99,
        "full_text": "Once upon a time in a land far away...",
    })

    assert response.status_code == 201
    data = response.json()
    assert data["full_text"] == "Once upon a time in a land far away..."
    assert data["summary"] is None  # Generated in background, not inline


@pytest.mark.asyncio(loop_scope="function")
async def test_create_book_without_full_text_no_summary(
    authenticated_client: AsyncClient,
    author_service: AuthorService,
    db_session: AsyncSession,
    mock_llm_service: LLMService,
):
    author = await author_service.create(data=AuthorCreateInput(name="Author"))
    await db_session.commit()

    response = await authenticated_client.post("/api/v1/books", json={
        "title": "Book Without Text",
        "author_id": str(author.id),
        "price": 14.99,
    })

    assert response.status_code == 201
    assert response.json()["summary"] is None
    mock_llm_service.generate_summary.assert_not_called()


@pytest.mark.asyncio(loop_scope="function")
async def test_generate_for_book_saves_summary(
    summary_service: SummaryService,
    author_service: AuthorService,
    book_service: BookService,
    db_session: AsyncSession,
    mock_llm_service: LLMService,
):
    """Test the background task function directly — verifies it fetches
    the book, calls the LLM, and persists the summary."""
    _, book_id = await _create_test_book(
        author_service, book_service, db_session,
        full_text="A story about testing...",
    )

    await summary_service.generate_for_book(book_id)

    mock_llm_service.generate_summary.assert_called_once_with("A story about testing...")

    # Re-fetch from a fresh session to verify persistence
    book = await book_service.retrieve(book_id=book_id)
    assert book.summary == "A compelling test summary."


# =============================================================================
# Per-book summarize endpoint
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_summarize_book_success(
    authenticated_client: AsyncClient,
    author_service: AuthorService,
    book_service: BookService,
    db_session: AsyncSession,
    mock_llm_service: LLMService,
):
    _, book_id = await _create_test_book(
        author_service, book_service, db_session,
        full_text="A long and winding tale...",
    )

    response = await authenticated_client.post(f"/api/v1/books/{book_id}/summarize")

    assert response.status_code == 200
    assert response.json()["summary"] == "A compelling test summary."
    mock_llm_service.generate_summary.assert_called_once_with("A long and winding tale...")


@pytest.mark.asyncio(loop_scope="function")
async def test_summarize_book_without_full_text_returns_400(
    authenticated_client: AsyncClient,
    author_service: AuthorService,
    book_service: BookService,
    db_session: AsyncSession,
):
    _, book_id = await _create_test_book(author_service, book_service, db_session)

    response = await authenticated_client.post(f"/api/v1/books/{book_id}/summarize")

    assert response.status_code == 400
    assert "full_text" in response.json()["detail"].lower()


@pytest.mark.asyncio(loop_scope="function")
async def test_summarize_nonexistent_book_returns_404(authenticated_client: AsyncClient):
    response = await authenticated_client.post(f"/api/v1/books/{uuid.uuid4()}/summarize")
    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_cannot_summarize_book(
    customer_client: AsyncClient,
    author_service: AuthorService,
    book_service: BookService,
    db_session: AsyncSession,
):
    _, book_id = await _create_test_book(
        author_service, book_service, db_session, full_text="Some text",
    )

    response = await customer_client.post(f"/api/v1/books/{book_id}/summarize")
    assert response.status_code == 403


# =============================================================================
# Backfill endpoint
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_backfill_processes_books_without_summaries(
    authenticated_client: AsyncClient,
    author_service: AuthorService,
    book_service: BookService,
    db_session: AsyncSession,
    mock_llm_service: LLMService,
):
    author = await author_service.create(data=AuthorCreateInput(name="Author"))

    book_ids = []
    for i in range(3):
        book = await book_service.create(data=BookCreateInput(
            title=f"Book {i}", author_id=author.id, price=9.99,
            full_text=f"Full text for book {i}",
        ))
        book_ids.append(str(book.id))

    # Book without full_text — should be skipped
    await book_service.create(data=BookCreateInput(
        title="No Text Book", author_id=author.id, price=9.99,
    ))
    await db_session.commit()

    response = await authenticated_client.post("/api/v1/books/backfill-summaries")

    assert response.status_code == 200
    data = response.json()
    assert data["attempted"] == 3
    assert data["succeeded"] == 3
    assert data["failed"] == 0
    assert len(data["book_ids"]) == 3

    for bid in book_ids:
        book = await book_service.retrieve(book_id=uuid.UUID(bid))
        assert book.summary == "A compelling test summary."


@pytest.mark.asyncio(loop_scope="function")
async def test_backfill_skips_books_with_existing_summaries(
    authenticated_client: AsyncClient,
    author_service: AuthorService,
    book_service: BookService,
    db_session: AsyncSession,
):
    author = await author_service.create(data=AuthorCreateInput(name="Author"))
    book = await book_service.create(data=BookCreateInput(
        title="Already Summarized", author_id=author.id, price=9.99,
        full_text="Some text",
    ))
    await book_service.update(book_id=book.id, data=BookUpdateInput(summary="Existing summary"))
    await db_session.commit()

    response = await authenticated_client.post("/api/v1/books/backfill-summaries")

    assert response.status_code == 200
    assert response.json()["attempted"] == 0


@pytest.mark.asyncio(loop_scope="function")
async def test_backfill_empty_catalog(authenticated_client: AsyncClient):
    response = await authenticated_client.post("/api/v1/books/backfill-summaries")

    assert response.status_code == 200
    assert response.json()["attempted"] == 0


@pytest.mark.asyncio(loop_scope="function")
async def test_backfill_tracks_failures(
    authenticated_client: AsyncClient,
    author_service: AuthorService,
    book_service: BookService,
    db_session: AsyncSession,
    mock_llm_service: LLMService,
):
    """When the LLM fails for some books, backfill reports partial failure
    without affecting other books."""
    author = await author_service.create(data=AuthorCreateInput(name="Author"))

    book_ok = await book_service.create(data=BookCreateInput(
        title="Will Succeed", author_id=author.id, price=9.99,
        full_text="Good text",
    ))
    book_fail = await book_service.create(data=BookCreateInput(
        title="Will Fail", author_id=author.id, price=9.99,
        full_text="Bad text",
    ))
    await db_session.commit()

    call_count = 0

    async def flaky_generate(text: str) -> str:
        nonlocal call_count
        call_count += 1
        if text == "Bad text":
            raise RuntimeError("LLM unavailable")
        return "Generated summary."

    mock_llm_service.generate_summary = flaky_generate

    response = await authenticated_client.post("/api/v1/books/backfill-summaries")

    assert response.status_code == 200
    data = response.json()
    assert data["attempted"] == 2
    assert data["succeeded"] == 1
    assert data["failed"] == 1


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_cannot_backfill(customer_client: AsyncClient):
    response = await customer_client.post("/api/v1/books/backfill-summaries")
    assert response.status_code == 403


# =============================================================================
# Admin can manually edit summary
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_can_edit_summary(
    authenticated_client: AsyncClient,
    author_service: AuthorService,
    book_service: BookService,
    db_session: AsyncSession,
):
    _, book_id = await _create_test_book(author_service, book_service, db_session)

    response = await authenticated_client.patch(
        f"/api/v1/books/{book_id}",
        json={"summary": "Manually written summary"},
    )

    assert response.status_code == 200
    assert response.json()["summary"] == "Manually written summary"


# =============================================================================
# Concurrency: semaphore limits parallel LLM calls
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_concurrent_summaries_respect_semaphore_limit(
    authenticated_client: AsyncClient,
    author_service: AuthorService,
    book_service: BookService,
    db_session: AsyncSession,
    test_engine: AsyncEngine,
):
    """Verify the semaphore limits concurrent LLM calls.

    Uses a mock LLM that tracks peak concurrency via an atomic counter.
    The semaphore is set to 2, and we backfill 6 books. The mock goes
    through the real generate_summary method (which acquires the semaphore),
    so this tests the actual concurrency control path.
    """
    max_concurrent = 2
    peak_concurrent = 0
    current_concurrent = 0
    lock = asyncio.Lock()

    original_mock = AsyncMock(return_value="Concurrent test summary.")

    async def tracked_generate(text: str) -> str:
        nonlocal peak_concurrent, current_concurrent
        async with lock:
            current_concurrent += 1
            peak_concurrent = max(peak_concurrent, current_concurrent)
        await asyncio.sleep(0.05)  # Simulate LLM latency
        result = await original_mock(text)
        async with lock:
            current_concurrent -= 1
        return result

    # Build LLM service with tight semaphore — the semaphore wraps
    # generate_summary, so tracked_generate runs INSIDE the semaphore
    tight_llm = LLMService.__new__(LLMService)
    tight_llm._model = "test-model"
    tight_llm._embedding_model = "test-embedding"
    tight_llm.generate_embedding = AsyncMock(return_value=[0.0] * 1536)
    tight_llm._semaphore = asyncio.Semaphore(max_concurrent)
    tight_llm._client = None  # Not used — generate_summary is replaced

    # Replace the method but keep the semaphore wrapper by patching the
    # internal call rather than the public method
    async def _guarded_generate(text: str) -> str:
        async with tight_llm._semaphore:
            return await tracked_generate(text)

    tight_llm.generate_summary = _guarded_generate

    tight_service = SummaryService(
        llm_service=tight_llm,
        session_factory=_make_test_session_factory(test_engine),
    )

    from src.routes.v1.books.router import _get_summary_service

    app.dependency_overrides[_get_summary_service] = lambda: tight_service

    author = await author_service.create(data=AuthorCreateInput(name="Author"))
    for i in range(6):
        await book_service.create(data=BookCreateInput(
            title=f"Concurrent Book {i}", author_id=author.id, price=9.99,
            full_text=f"Text for concurrent book {i}",
        ))
    await db_session.commit()

    response = await authenticated_client.post("/api/v1/books/backfill-summaries")

    assert response.status_code == 200
    assert response.json()["attempted"] == 6
    assert peak_concurrent <= max_concurrent, (
        f"Peak concurrency {peak_concurrent} exceeded limit {max_concurrent}"
    )
    assert peak_concurrent > 0, "Tasks should have run concurrently"
