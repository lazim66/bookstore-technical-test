import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.exc import NoResultFound
from sqlmodel.ext.asyncio.session import AsyncSession
from src.db.models import DBAuthor
from src.db.operations import get_db_session
from src.routes.v1.authors.repository import AuthorRepository
from src.routes.v1.authors.schema import AuthorCreateInput, AuthorUpdateInput


class AuthorNotFound(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=404, detail="Author not found")


async def get_author_service(db_session: AsyncSession = Depends(get_db_session)) -> "AuthorService":
    return AuthorService(db_session=db_session)


class AuthorService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.repository = AuthorRepository(db_session=db_session)

    async def create(self, data: AuthorCreateInput) -> DBAuthor:
        return await self.repository.create(data=data)

    async def retrieve(self, author_id: uuid.UUID) -> DBAuthor:
        try:
            return await self.repository.retrieve(author_id=author_id)
        except NoResultFound as exc:
            raise AuthorNotFound from exc

    async def list(self) -> list[DBAuthor]:
        return await self.repository.list()

    async def update(self, author_id: uuid.UUID, data: AuthorUpdateInput) -> DBAuthor:
        author = await self.retrieve(author_id=author_id)
        return await self.repository.update(author_id=author.id, **data.model_dump(exclude_unset=True))

    async def delete(self, author_id: uuid.UUID) -> None:
        author = await self.retrieve(author_id=author_id)
        await self.repository.delete(author_id=author.id)
