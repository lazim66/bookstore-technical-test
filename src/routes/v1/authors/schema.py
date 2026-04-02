from uuid import UUID

from pydantic import BaseModel, Field


class AuthorCreateInput(BaseModel):
    name: str = Field(min_length=1)
    bio: str | None = None


class AuthorUpdateInput(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    bio: str | None = None


class AuthorOutput(BaseModel):
    id: UUID
    name: str
    bio: str | None
