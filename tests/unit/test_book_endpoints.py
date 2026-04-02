"""Tests for book endpoints."""

import uuid
from uuid import UUID

import pytest
from httpx import AsyncClient
from src.routes.v1.books.service import BookService


@pytest.mark.asyncio(loop_scope="function")
async def test_create_book_success(authenticated_client: AsyncClient, book_service: BookService):
    # Create test author via API first
    author_data = {"name": "Test Author", "bio": "Test bio"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    book_data = {
        "title": "Great Book",
        "author_id": author["id"],
        "description": "A wonderful book",
        "price": 29.99,
        "published_date": "2024-01-15T10:00:00",
    }

    response = await authenticated_client.post("/api/v1/books", json=book_data)

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == book_data["title"]
    assert data["author_id"] == author["id"]
    assert data["description"] == book_data["description"]
    assert data["price"] == book_data["price"]
    assert data["id"] is not None

    # Verify book was created in database
    created_book = await book_service.retrieve(book_id=UUID(data["id"]))
    assert created_book.title == book_data["title"]
    assert str(created_book.author_id) == author["id"]


@pytest.mark.asyncio(loop_scope="function")
async def test_create_book_without_optional_fields(authenticated_client: AsyncClient):
    # Create test author via API first
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    book_data = {
        "title": "Simple Book",
        "author_id": author["id"],
        "price": 19.99,
    }

    response = await authenticated_client.post("/api/v1/books", json=book_data)

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == book_data["title"]
    assert data["description"] is None
    assert data["published_date"] is None


@pytest.mark.asyncio(loop_scope="function")
async def test_create_book_invalid_price(authenticated_client: AsyncClient):
    # Create test author via API first
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    book_data = {
        "title": "Bad Book",
        "author_id": author["id"],
        "price": -10.00,
    }

    response = await authenticated_client.post("/api/v1/books", json=book_data)

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="function")
async def test_create_book_zero_price(authenticated_client: AsyncClient):
    # Create test author via API first
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    book_data = {
        "title": "Free Book",
        "author_id": author["id"],
        "price": 0,
    }

    response = await authenticated_client.post("/api/v1/books", json=book_data)

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="function")
async def test_create_book_empty_title(authenticated_client: AsyncClient):
    # Create test author via API first
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    book_data = {
        "title": "",
        "author_id": author["id"],
        "price": 15.99,
    }

    response = await authenticated_client.post("/api/v1/books", json=book_data)

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="function")
async def test_list_books_empty(authenticated_client: AsyncClient):
    response = await authenticated_client.get("/api/v1/books")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio(loop_scope="function")
async def test_list_books_with_data(authenticated_client: AsyncClient):
    # Create test author via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    # Create test books via API
    book1_data = {"title": "Book One", "author_id": author["id"], "price": 19.99, "description": "First book"}
    book1_response = await authenticated_client.post("/api/v1/books", json=book1_data)
    assert book1_response.status_code == 201
    book1 = book1_response.json()

    book2_data = {"title": "Book Two", "author_id": author["id"], "price": 29.99}
    book2_response = await authenticated_client.post("/api/v1/books", json=book2_data)
    assert book2_response.status_code == 201
    book2 = book2_response.json()

    response = await authenticated_client.get("/api/v1/books")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert any(b["id"] == book1["id"] for b in data)
    assert any(b["id"] == book2["id"] for b in data)


@pytest.mark.asyncio(loop_scope="function")
async def test_get_book_success(authenticated_client: AsyncClient):
    # Create test author and book via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    book_data = {"title": "Test Book", "author_id": author["id"], "description": "Test description", "price": 24.99}
    create_response = await authenticated_client.post("/api/v1/books", json=book_data)
    assert create_response.status_code == 201
    created_book = create_response.json()

    response = await authenticated_client.get(f"/api/v1/books/{created_book['id']}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created_book["id"]
    assert data["title"] == "Test Book"
    assert data["description"] == "Test description"
    assert data["price"] == 24.99


@pytest.mark.asyncio(loop_scope="function")
async def test_get_book_not_found(authenticated_client: AsyncClient):
    random_id = uuid.uuid4()
    response = await authenticated_client.get(f"/api/v1/books/{random_id}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio(loop_scope="function")
async def test_update_book_title(authenticated_client: AsyncClient, book_service: BookService):
    # Create test author and book via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    book_data = {"title": "Original Title", "author_id": author["id"], "price": 19.99}
    create_response = await authenticated_client.post("/api/v1/books", json=book_data)
    assert create_response.status_code == 201
    created_book = create_response.json()

    update_data = {
        "title": "Updated Title",
    }

    response = await authenticated_client.patch(f"/api/v1/books/{created_book['id']}", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["price"] == 19.99

    # Verify title was updated in database
    updated_book = await book_service.retrieve(book_id=UUID(created_book["id"]))
    assert updated_book.title == "Updated Title"


@pytest.mark.asyncio(loop_scope="function")
async def test_update_book_price(authenticated_client: AsyncClient, book_service: BookService):
    # Create test author and book via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    book_data = {"title": "Test Book", "author_id": author["id"], "price": 19.99}
    create_response = await authenticated_client.post("/api/v1/books", json=book_data)
    assert create_response.status_code == 201
    created_book = create_response.json()

    update_data = {
        "price": 29.99,
    }

    response = await authenticated_client.patch(f"/api/v1/books/{created_book['id']}", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["price"] == 29.99

    # Verify price was updated in database
    updated_book = await book_service.retrieve(book_id=UUID(created_book["id"]))
    assert updated_book.price == 29.99


@pytest.mark.asyncio(loop_scope="function")
async def test_update_book_description(authenticated_client: AsyncClient, book_service: BookService):
    # Create test author and book via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    book_data = {"title": "Test Book", "author_id": author["id"], "price": 19.99}
    create_response = await authenticated_client.post("/api/v1/books", json=book_data)
    assert create_response.status_code == 201
    created_book = create_response.json()

    update_data = {
        "description": "New description",
    }

    response = await authenticated_client.patch(f"/api/v1/books/{created_book['id']}", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "New description"


@pytest.mark.asyncio(loop_scope="function")
async def test_update_book_invalid_price(authenticated_client: AsyncClient):
    # Create test author and book via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    book_data = {"title": "Test Book", "author_id": author["id"], "price": 19.99}
    create_response = await authenticated_client.post("/api/v1/books", json=book_data)
    assert create_response.status_code == 201
    created_book = create_response.json()

    update_data = {
        "price": -5.00,
    }

    response = await authenticated_client.patch(f"/api/v1/books/{created_book['id']}", json=update_data)

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="function")
async def test_update_book_not_found(authenticated_client: AsyncClient):
    random_id = uuid.uuid4()
    update_data = {
        "title": "New Title",
    }

    response = await authenticated_client.patch(f"/api/v1/books/{random_id}", json=update_data)

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="function")
async def test_delete_book_success(authenticated_client: AsyncClient, book_service: BookService):
    # Create test author and book via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    book_data = {"title": "To Delete", "author_id": author["id"], "price": 19.99}
    create_response = await authenticated_client.post("/api/v1/books", json=book_data)
    assert create_response.status_code == 201
    created_book = create_response.json()

    response = await authenticated_client.delete(f"/api/v1/books/{created_book['id']}")

    assert response.status_code == 204

    # Verify book was deleted from database
    with pytest.raises(Exception):
        await book_service.retrieve(book_id=UUID(created_book["id"]))


@pytest.mark.asyncio(loop_scope="function")
async def test_delete_book_not_found(authenticated_client: AsyncClient):
    random_id = uuid.uuid4()
    response = await authenticated_client.delete(f"/api/v1/books/{random_id}")

    assert response.status_code == 404
