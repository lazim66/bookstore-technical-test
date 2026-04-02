from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from src.db.models import DBUser
from src.routes.v1.users.schema import AdminUserCreateInput, UserSignUpInput


class UserRepository:
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def create(self, data: UserSignUpInput | AdminUserCreateInput) -> DBUser:
        user = DBUser(**data.model_dump())
        return await self.db_session.create(user)

    async def retrieve(self, user_id: UUID) -> DBUser:
        stmt = select(DBUser).where(DBUser.id == user_id)
        result = await self.db_session.exec(stmt)
        return result.one()

    async def retrieve_by_email(self, email: str) -> DBUser:
        stmt = select(DBUser).where(DBUser.email == email)
        result = await self.db_session.exec(stmt)
        return result.one()

    async def update(self, user_id: UUID, **kwargs) -> DBUser:
        user = await self.retrieve(user_id)
        for key, value in kwargs.items():
            setattr(user, key, value)
        return await self.db_session.update(user)

    async def delete(self, user_id: UUID) -> None:
        user = await self.retrieve(user_id)
        await self.db_session.delete(user)
