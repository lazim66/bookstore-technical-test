from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BookCreateInput(BaseModel):
    title: str = Field(min_length=1)
    author_id: UUID
    description: str | None = None
    price: float = Field(gt=0)
    published_date: datetime | None = None


class BookUpdateInput(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    author_id: UUID | None = None
    description: str | None = None
    price: float | None = Field(default=None, gt=0)
    published_date: datetime | None = None


class BookOutput(BaseModel):
    id: UUID
    title: str
    author_id: UUID
    description: str | None
    price: float
    published_date: datetime | None
