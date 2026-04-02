"""Service for generating book summaries and embeddings.

Separated from BookService because these operations:
- Run asynchronously (background tasks after book creation)
- Need independent DB sessions for concurrent operations
- Have different dependencies (LLM service)

Provides two modes of operation:
- Pure functions (generate_summary_text, generate_embedding_for_text):
  No DB interaction — the caller manages persistence. Used by synchronous endpoints.
- Self-contained operations (generate_for_book, generate_embedding_for_book):
  Own DB session, safe for background tasks and asyncio.gather.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator, Callable

from pydantic import BaseModel
from sqlmodel import select

from src.db.models import DBBook
from src.db.operations import managed_session
from src.utils.llm import LLMService, compose_embedding_text

logger = logging.getLogger(__name__)


class BackfillResult(BaseModel):
    attempted: int
    succeeded: int
    failed: int
    book_ids: list[uuid.UUID]


class SummaryService:
    def __init__(
        self,
        llm_service: LLMService,
        session_factory: Callable[..., AsyncGenerator] | None = None,
    ) -> None:
        self._llm = llm_service
        self._session_factory = session_factory or managed_session

    # ── Pure LLM calls (no DB) ───────────────────────────────────────────

    async def generate_summary_text(self, full_text: str) -> str:
        """Generate a summary from text. Caller handles persistence."""
        return await self._llm.generate_summary(full_text)

    async def generate_embedding_for_text(
        self, title: str, description: str | None, summary: str | None
    ) -> list[float]:
        """Generate an embedding from book metadata. Caller handles persistence."""
        text = compose_embedding_text(title, description, summary)
        return await self._llm.generate_embedding(text)

    async def generate_query_embedding(self, query: str) -> list[float]:
        """Generate an embedding for a search query (raw text, no formatting)."""
        return await self._llm.generate_embedding(query)

    # ── Self-contained operations (own DB session) ───────────────────────

    async def _fetch_book(self, session, book_id: uuid.UUID, label: str) -> DBBook | None:
        """Fetch a book by ID from the given session, logging a warning if not found."""
        stmt = select(DBBook).where(DBBook.id == book_id)
        result = await session.exec(stmt)
        book = result.first()
        if not book:
            logger.warning("Book %s not found for %s", book_id, label)
        return book

    async def generate_for_book(self, book_id: uuid.UUID) -> bool:
        """Generate summary AND embedding for a single book.

        Creates its own DB session, making it safe to run concurrently
        via asyncio.gather and as a background task.

        Flow: fetch book -> generate summary -> generate embedding -> persist both.
        Returns True if successful, False otherwise.
        """
        async with self._session_factory() as session:
            book = await self._fetch_book(session, book_id, "generation")
            if not book:
                return False

            if not book.full_text:
                logger.info("Book %s has no full_text, skipping", book_id)
                return False

            try:
                summary = await self._llm.generate_summary(book.full_text)
                book.summary = summary

                text = compose_embedding_text(book.title, book.description, summary)
                book.embedding = await self._llm.generate_embedding(text)

                await session.flush()
                logger.info("Summary and embedding saved for book %s", book_id)
                return True
            except Exception:
                logger.exception("Failed to generate for book %s", book_id)
                return False

    async def generate_embedding_for_book(self, book_id: uuid.UUID) -> bool:
        """Generate (or regenerate) the embedding for a single book.

        Uses the book's current title, description, and summary.
        Own DB session -- safe for concurrent use.
        """
        async with self._session_factory() as session:
            book = await self._fetch_book(session, book_id, "embedding")
            if not book:
                return False

            try:
                text = compose_embedding_text(book.title, book.description, book.summary)
                book.embedding = await self._llm.generate_embedding(text)
                await session.flush()
                logger.info("Embedding saved for book %s", book_id)
                return True
            except Exception:
                logger.exception("Failed to generate embedding for book %s", book_id)
                return False

    # ── Backfill operations ──────────────────────────────────────────────

    async def _run_backfill(
        self,
        where_clauses: list,
        task_fn: Callable[[uuid.UUID], asyncio.coroutines],
        label: str,
    ) -> BackfillResult:
        """Shared backfill logic: query matching book IDs, run task_fn on each concurrently."""
        async with self._session_factory() as session:
            stmt = select(DBBook.id).where(*where_clauses)
            result = await session.exec(stmt)
            book_ids = list(result.all())

        if not book_ids:
            logger.info("No books need %s backfill", label)
            return BackfillResult(attempted=0, succeeded=0, failed=0, book_ids=[])

        logger.info("Backfilling %s for %d books", label, len(book_ids))

        results = await asyncio.gather(
            *(task_fn(book_id) for book_id in book_ids)
        )

        succeeded = sum(1 for r in results if r)
        failed = len(book_ids) - succeeded
        logger.info("Backfill complete: %d succeeded, %d failed", succeeded, failed)

        return BackfillResult(
            attempted=len(book_ids),
            succeeded=succeeded,
            failed=failed,
            book_ids=book_ids,
        )

    async def backfill(self) -> BackfillResult:
        """Generate summaries and embeddings for books that need them.

        Targets books with full_text but no summary. Each book gets its own
        DB session. The LLM service's semaphore controls parallelism.
        """
        return await self._run_backfill(
            where_clauses=[
                DBBook.full_text.isnot(None),  # noqa: E711
                DBBook.summary.is_(None),  # noqa: E711
            ],
            task_fn=self.generate_for_book,
            label="summaries and embeddings",
        )

    async def backfill_embeddings(self) -> BackfillResult:
        """Regenerate embeddings for all books that have no embedding.

        Useful after bulk summary generation, or for books created before
        the embedding feature existed.
        """
        return await self._run_backfill(
            where_clauses=[DBBook.embedding.is_(None)],  # noqa: E711
            task_fn=self.generate_embedding_for_book,
            label="embeddings",
        )
