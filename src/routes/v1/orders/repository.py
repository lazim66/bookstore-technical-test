from __future__ import annotations

from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from src.db.models import DBOrder
from src.routes.v1.orders.schema import OrderCreateInput


class OrderRepository:
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def create(self, user_id: UUID, data: OrderCreateInput, total_amount: float) -> DBOrder:
        order = DBOrder(user_id=user_id, **data.model_dump(), total_amount=total_amount)
        return await self.db_session.create(order)

    async def retrieve(self, order_id: UUID) -> DBOrder:
        stmt = select(DBOrder).where(DBOrder.id == order_id)
        result = await self.db_session.exec(stmt)
        return result.one()

    async def retrieve_by_user(self, user_id: UUID, order_id: UUID) -> DBOrder:
        stmt = select(DBOrder).where(DBOrder.id == order_id, DBOrder.user_id == user_id)
        result = await self.db_session.exec(stmt)
        return result.one()

    async def list(self) -> list[DBOrder]:
        stmt = select(DBOrder)
        result = await self.db_session.exec(stmt)
        return result.all()

    async def list_by_user(self, user_id: UUID) -> list[DBOrder]:
        stmt = select(DBOrder).where(DBOrder.user_id == user_id)
        result = await self.db_session.exec(stmt)
        return result.all()

    async def update(self, user_id: UUID, order_id: UUID, **kwargs) -> DBOrder:
        order = await self.retrieve_by_user(user_id=user_id, order_id=order_id)
        for key, value in kwargs.items():
            setattr(order, key, value)
        return await self.db_session.update(order)

    async def delete(self, user_id: UUID, order_id: UUID) -> None:
        order = await self.retrieve_by_user(user_id=user_id, order_id=order_id)
        await self.db_session.delete(order)
