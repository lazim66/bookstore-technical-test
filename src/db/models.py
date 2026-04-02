"""Database models using SQLModel."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class DBUser(SQLModel, table=True):
    """User model for authentication and user management."""

    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    full_name: str
    hashed_password: str
    role: str = Field(default="customer", index=True)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"onupdate": datetime.utcnow})


class DBAuthor(SQLModel, table=True):
    """Author model for book authors."""

    __tablename__ = "authors"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    bio: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"onupdate": datetime.utcnow})


class DBBook(SQLModel, table=True):
    """Book model for book catalog."""

    __tablename__ = "books"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    title: str = Field(index=True)
    author_id: UUID = Field(foreign_key="authors.id", index=True)
    description: str | None = Field(default=None)
    full_text: str | None = Field(default=None)
    summary: str | None = Field(default=None)
    price: float
    published_date: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"onupdate": datetime.utcnow})


class DBOrder(SQLModel, table=True):
    """Order model for user orders."""

    __tablename__ = "orders"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    book_id: UUID = Field(foreign_key="books.id", index=True)
    quantity: int = Field(default=1)
    total_amount: float
    status: str = Field(default="pending", index=True)  # pending, completed, cancelled
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"onupdate": datetime.utcnow})
