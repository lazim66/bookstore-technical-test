from uuid import UUID

from pydantic import BaseModel, Field


class OrderCreateInput(BaseModel):
    book_id: UUID
    quantity: int = Field(default=1, gt=0)


class OrderUpdateInput(BaseModel):
    quantity: int | None = Field(default=None, gt=0)
    status: str | None = None


class OrderOutput(BaseModel):
    id: UUID
    user_id: UUID
    book_id: UUID
    quantity: int
    total_amount: float
    status: str
