import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.exc import NoResultFound
from sqlmodel.ext.asyncio.session import AsyncSession
from src.db.models import DBBook
from src.db.operations import get_db_session
from src.routes.v1.books.repository import BookRepository
from src.routes.v1.books.schema import BookCreateInput, BookUpdateInput


class BookNotFound(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=404, detail="Book not found")


async def get_book_service(db_session: AsyncSession = Depends(get_db_session)) -> "BookService":
    return BookService(db_session=db_session)


class BookService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.repository = BookRepository(db_session=db_session)

    async def create(self, data: BookCreateInput) -> DBBook:
        return await self.repository.create(data=data)

    async def retrieve(self, book_id: uuid.UUID) -> DBBook:
        try:
            return await self.repository.retrieve(book_id=book_id)
        except NoResultFound as exc:
            raise BookNotFound from exc

    async def list(self) -> list[DBBook]:
        return await self.repository.list()

    async def update(self, book_id: uuid.UUID, data: BookUpdateInput) -> DBBook:
        book = await self.retrieve(book_id=book_id)
        return await self.repository.update(book_id=book.id, **data.model_dump(exclude_unset=True))

    async def delete(self, book_id: uuid.UUID) -> None:
        book = await self.retrieve(book_id=book_id)
        await self.repository.delete(book_id=book.id)
