from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from src.db.models import DBAuthor
from src.routes.v1.authors.schema import AuthorCreateInput


class AuthorRepository:
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def create(self, data: AuthorCreateInput) -> DBAuthor:
        author = DBAuthor(**data.model_dump())
        return await self.db_session.create(author)

    async def retrieve(self, author_id: UUID) -> DBAuthor:
        stmt = select(DBAuthor).where(DBAuthor.id == author_id)
        result = await self.db_session.exec(stmt)
        return result.one()

    async def list(self) -> list[DBAuthor]:
        stmt = select(DBAuthor)
        result = await self.db_session.exec(stmt)
        return result.all()

    async def update(self, author_id: UUID, **kwargs) -> DBAuthor:
        author = await self.retrieve(author_id)
        for key, value in kwargs.items():
            setattr(author, key, value)
        return await self.db_session.update(author)

    async def delete(self, author_id: UUID) -> None:
        author = await self.retrieve(author_id)
        await self.db_session.delete(author)
