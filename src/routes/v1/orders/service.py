from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.exc import NoResultFound
from sqlmodel.ext.asyncio.session import AsyncSession
from src.db.models import DBOrder
from src.db.operations import get_db_session
from src.routes.v1.books.repository import BookRepository
from src.routes.v1.orders.repository import OrderRepository
from src.routes.v1.orders.schema import OrderCreateInput, OrderUpdateInput


class OrderNotFound(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=404, detail="Order not found")


class BookNotFound(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=404, detail="Book not found")


async def get_order_service(db_session: AsyncSession = Depends(get_db_session)) -> "OrderService":
    return OrderService(db_session=db_session)


class OrderService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.repository = OrderRepository(db_session=db_session)
        self.book_repository = BookRepository(db_session=db_session)

    async def _get_book_price(self, book_id: uuid.UUID) -> float:
        try:
            book = await self.book_repository.retrieve(book_id=book_id)
        except NoResultFound as exc:
            raise BookNotFound from exc
        return book.price

    async def create(self, data: OrderCreateInput, user_id: uuid.UUID) -> DBOrder:
        price = await self._get_book_price(data.book_id)
        total_amount = round(price * data.quantity, 2)
        return await self.repository.create(user_id=user_id, data=data, total_amount=total_amount)

    async def retrieve(self, order_id: uuid.UUID) -> DBOrder:
        try:
            return await self.repository.retrieve(order_id=order_id)
        except NoResultFound as exc:
            raise OrderNotFound from exc

    async def retrieve_by_user(self, order_id: uuid.UUID, user_id: uuid.UUID) -> DBOrder:
        try:
            return await self.repository.retrieve_by_user(user_id=user_id, order_id=order_id)
        except NoResultFound as exc:
            raise OrderNotFound from exc

    async def list(self) -> list[DBOrder]:
        return await self.repository.list()

    async def list_by_user(self, user_id: uuid.UUID) -> list[DBOrder]:
        return await self.repository.list_by_user(user_id=user_id)

    async def update(self, order_id: uuid.UUID, user_id: uuid.UUID, data: OrderUpdateInput) -> DBOrder:
        try:
            update_data = data.model_dump(exclude_unset=True)
            if "quantity" in update_data:
                order = await self.repository.retrieve_by_user(user_id=user_id, order_id=order_id)
                price = await self._get_book_price(order.book_id)
                update_data["total_amount"] = round(price * update_data["quantity"], 2)
            return await self.repository.update(user_id=user_id, order_id=order_id, **update_data)
        except NoResultFound as exc:
            raise OrderNotFound from exc

    async def delete(self, order_id: uuid.UUID, user_id: uuid.UUID) -> None:
        try:
            await self.repository.delete(user_id=user_id, order_id=order_id)
        except NoResultFound as exc:
            raise OrderNotFound from exc
