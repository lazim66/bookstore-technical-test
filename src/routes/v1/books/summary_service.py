"""Service for generating and backfilling book summaries.

Separated from BookService because summary generation:
- Runs asynchronously (background tasks after book creation)
- Needs independent DB sessions for concurrent operations
- Has different dependencies (LLM service)

The service provides two modes of operation:
- generate_summary_text(): Pure LLM call, returns text. Used by synchronous
  endpoints where the caller manages the DB session.
- generate_for_book(): Self-contained background operation with its own DB
  session. Used by background tasks and backfill (asyncio.gather).
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator, Callable

from pydantic import BaseModel
from sqlmodel import select

from src.db.models import DBBook
from src.db.operations import managed_session
from src.utils.llm import LLMService

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

    async def generate_summary_text(self, full_text: str) -> str:
        """Generate a summary from text. Pure LLM call — no DB interaction.

        Used by synchronous endpoints where the caller handles persistence.
        """
        return await self._llm.generate_summary(full_text)

    async def generate_for_book(self, book_id: uuid.UUID) -> bool:
        """Generate and persist a summary for a single book.

        Creates its own DB session, making it safe to run concurrently
        via asyncio.gather and as a background task (where the request
        session is already closed).

        Returns True if summary was generated, False otherwise.
        """
        async with self._session_factory() as session:
            stmt = select(DBBook).where(DBBook.id == book_id)
            result = await session.exec(stmt)
            book = result.first()

            if not book:
                logger.warning("Book %s not found for summary generation", book_id)
                return False

            if not book.full_text:
                logger.info("Book %s has no full_text, skipping summary", book_id)
                return False

            try:
                summary = await self._llm.generate_summary(book.full_text)
                book.summary = summary
                await session.flush()
                logger.info("Summary saved for book %s", book_id)
                return True
            except Exception:
                logger.exception("Failed to generate summary for book %s", book_id)
                return False

    async def backfill(self) -> BackfillResult:
        """Find all books with full_text but no summary, and generate summaries.

        Each book gets its own DB session and LLM call. The LLM service's
        semaphore controls how many run in parallel.
        """
        async with self._session_factory() as session:
            stmt = select(DBBook.id).where(
                DBBook.full_text.isnot(None),  # noqa: E711
                DBBook.summary.is_(None),  # noqa: E711
            )
            result = await session.exec(stmt)
            book_ids = list(result.all())

        if not book_ids:
            logger.info("No books need summary backfill")
            return BackfillResult(attempted=0, succeeded=0, failed=0, book_ids=[])

        logger.info("Backfilling summaries for %d books", len(book_ids))

        results = await asyncio.gather(
            *(self.generate_for_book(book_id) for book_id in book_ids)
        )

        succeeded = sum(1 for r in results if r)
        failed = sum(1 for r in results if not r)
        logger.info("Backfill complete: %d succeeded, %d failed", succeeded, failed)

        return BackfillResult(
            attempted=len(book_ids),
            succeeded=succeeded,
            failed=failed,
            book_ids=book_ids,
        )
