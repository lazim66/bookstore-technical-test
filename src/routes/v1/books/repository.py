from __future__ import annotations

from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from src.db.models import DBBook
from src.routes.v1.books.schema import BookCreateInput


class BookRepository:
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def create(self, data: BookCreateInput) -> DBBook:
        book = DBBook(**data.model_dump())
        return await self.db_session.create(book)

    async def retrieve(self, book_id: UUID) -> DBBook:
        stmt = select(DBBook).where(DBBook.id == book_id)
        result = await self.db_session.exec(stmt)
        return result.one()

    async def list(self) -> list[DBBook]:
        stmt = select(DBBook)
        result = await self.db_session.exec(stmt)
        return result.all()

    async def update(self, book_id: UUID, **kwargs) -> DBBook:
        book = await self.retrieve(book_id)
        for key, value in kwargs.items():
            setattr(book, key, value)
        return await self.db_session.update(book)

    async def delete(self, book_id: UUID) -> None:
        book = await self.retrieve(book_id)
        await self.db_session.delete(book)

    async def semantic_search(
        self, query_embedding: list[float], limit: int = 10
    ) -> list[tuple[DBBook, float]]:
        """Find books by cosine similarity to the query embedding.

        Returns (book, similarity_score) tuples ranked by relevance.
        Only includes books that have an embedding.
        Similarity is 1 - cosine_distance (higher = more similar).
        """
        distance = DBBook.embedding.cosine_distance(query_embedding)
        similarity = (1 - distance).label("similarity")

        stmt = (
            select(DBBook, similarity)
            .where(DBBook.embedding.isnot(None))  # noqa: E711
            .order_by(distance)
            .limit(limit)
        )
        result = await self.db_session.exec(stmt)
        return [(row[0], round(float(row[1]), 4)) for row in result.all()]
