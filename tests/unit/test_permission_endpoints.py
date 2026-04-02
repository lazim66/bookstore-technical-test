"""Tests for role-based access control (permissions).

Verifies that:
- Admin users can perform catalog management operations (create/update/delete books and authors)
- Customer users are denied catalog management operations with 403
- Customer users can still browse the catalog (list/get books and authors)
- Customer users can manage their own orders
- Admin user creation and role promotion endpoints are admin-only
- Signup always creates a customer (role cannot be self-assigned)
"""

import uuid

import pytest
from httpx import AsyncClient
from src.db.models import DBAuthor, DBBook, DBUser
from src.routes.v1.authors.schema import AuthorCreateInput
from src.routes.v1.authors.service import AuthorService
from src.routes.v1.books.schema import BookCreateInput
from src.routes.v1.books.service import BookService
from src.routes.v1.users.service import UserService


# =============================================================================
# Authors — Customer denied on write operations
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_cannot_create_author(customer_client: AsyncClient):
    response = await customer_client.post("/api/v1/authors", json={"name": "New Author"})
    assert response.status_code == 403


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_cannot_update_author(
    customer_client: AsyncClient, author_service: AuthorService
):
    author = await author_service.create(data=AuthorCreateInput(name="Existing Author"))
    response = await customer_client.patch(
        f"/api/v1/authors/{author.id}", json={"name": "Changed"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_cannot_delete_author(
    customer_client: AsyncClient, author_service: AuthorService
):
    author = await author_service.create(data=AuthorCreateInput(name="To Delete"))
    response = await customer_client.delete(f"/api/v1/authors/{author.id}")
    assert response.status_code == 403


# =============================================================================
# Authors — Customer allowed on read operations
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_can_list_authors(
    customer_client: AsyncClient, author_service: AuthorService
):
    await author_service.create(data=AuthorCreateInput(name="Visible Author"))
    response = await customer_client.get("/api/v1/authors")
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_can_get_author(
    customer_client: AsyncClient, author_service: AuthorService
):
    author = await author_service.create(data=AuthorCreateInput(name="Specific Author"))
    response = await customer_client.get(f"/api/v1/authors/{author.id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Specific Author"


# =============================================================================
# Authors — Admin allowed on write operations
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_can_create_author(authenticated_client: AsyncClient):
    response = await authenticated_client.post(
        "/api/v1/authors", json={"name": "Admin Author", "bio": "Created by admin"}
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Admin Author"


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_can_update_author(
    authenticated_client: AsyncClient, author_service: AuthorService
):
    author = await author_service.create(data=AuthorCreateInput(name="Original"))
    response = await authenticated_client.patch(
        f"/api/v1/authors/{author.id}", json={"name": "Updated"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated"


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_can_delete_author(
    authenticated_client: AsyncClient, author_service: AuthorService
):
    author = await author_service.create(data=AuthorCreateInput(name="To Delete"))
    response = await authenticated_client.delete(f"/api/v1/authors/{author.id}")
    assert response.status_code == 204


# =============================================================================
# Books — Customer denied on write operations
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_cannot_create_book(
    customer_client: AsyncClient, author_service: AuthorService
):
    author = await author_service.create(data=AuthorCreateInput(name="Author"))
    response = await customer_client.post(
        "/api/v1/books",
        json={"title": "Forbidden Book", "author_id": str(author.id), "price": 9.99},
    )
    assert response.status_code == 403


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_cannot_update_book(
    customer_client: AsyncClient, author_service: AuthorService, book_service: BookService
):
    author = await author_service.create(data=AuthorCreateInput(name="Author"))
    book = await book_service.create(
        data=BookCreateInput(title="Test Book", author_id=author.id, price=19.99)
    )
    response = await customer_client.patch(
        f"/api/v1/books/{book.id}", json={"title": "Changed"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_cannot_delete_book(
    customer_client: AsyncClient, author_service: AuthorService, book_service: BookService
):
    author = await author_service.create(data=AuthorCreateInput(name="Author"))
    book = await book_service.create(
        data=BookCreateInput(title="Test Book", author_id=author.id, price=19.99)
    )
    response = await customer_client.delete(f"/api/v1/books/{book.id}")
    assert response.status_code == 403


# =============================================================================
# Books — Customer allowed on read operations
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_can_list_books(
    customer_client: AsyncClient, author_service: AuthorService, book_service: BookService
):
    author = await author_service.create(data=AuthorCreateInput(name="Author"))
    await book_service.create(
        data=BookCreateInput(title="Visible Book", author_id=author.id, price=14.99)
    )
    response = await customer_client.get("/api/v1/books")
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_can_get_book(
    customer_client: AsyncClient, author_service: AuthorService, book_service: BookService
):
    author = await author_service.create(data=AuthorCreateInput(name="Author"))
    book = await book_service.create(
        data=BookCreateInput(title="Specific Book", author_id=author.id, price=24.99)
    )
    response = await customer_client.get(f"/api/v1/books/{book.id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Specific Book"


# =============================================================================
# Books — Admin allowed on write operations
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_can_create_book(
    authenticated_client: AsyncClient, author_service: AuthorService
):
    author = await author_service.create(data=AuthorCreateInput(name="Author"))
    response = await authenticated_client.post(
        "/api/v1/books",
        json={"title": "Admin Book", "author_id": str(author.id), "price": 19.99},
    )
    assert response.status_code == 201
    assert response.json()["title"] == "Admin Book"


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_can_update_book(
    authenticated_client: AsyncClient, author_service: AuthorService, book_service: BookService
):
    author = await author_service.create(data=AuthorCreateInput(name="Author"))
    book = await book_service.create(
        data=BookCreateInput(title="Original", author_id=author.id, price=19.99)
    )
    response = await authenticated_client.patch(
        f"/api/v1/books/{book.id}", json={"title": "Updated"}
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated"


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_can_delete_book(
    authenticated_client: AsyncClient, author_service: AuthorService, book_service: BookService
):
    author = await author_service.create(data=AuthorCreateInput(name="Author"))
    book = await book_service.create(
        data=BookCreateInput(title="To Delete", author_id=author.id, price=19.99)
    )
    response = await authenticated_client.delete(f"/api/v1/books/{book.id}")
    assert response.status_code == 204


# =============================================================================
# Orders — Customer can manage own orders
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_can_create_order(
    customer_client: AsyncClient, author_service: AuthorService, book_service: BookService
):
    author = await author_service.create(data=AuthorCreateInput(name="Author"))
    book = await book_service.create(
        data=BookCreateInput(title="Orderable Book", author_id=author.id, price=19.99)
    )
    response = await customer_client.post(
        "/api/v1/orders", json={"book_id": str(book.id), "quantity": 1}
    )
    assert response.status_code == 201
    assert response.json()["book_id"] == str(book.id)


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_can_list_own_orders(
    customer_client: AsyncClient, author_service: AuthorService, book_service: BookService
):
    author = await author_service.create(data=AuthorCreateInput(name="Author"))
    book = await book_service.create(
        data=BookCreateInput(title="Book", author_id=author.id, price=19.99)
    )
    await customer_client.post(
        "/api/v1/orders", json={"book_id": str(book.id), "quantity": 1}
    )
    response = await customer_client.get("/api/v1/orders")
    assert response.status_code == 200
    assert len(response.json()) == 1


# =============================================================================
# Admin user creation endpoint
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_can_create_user(authenticated_client: AsyncClient):
    user_data = {
        "email": f"new_{uuid.uuid4()}@example.com",
        "full_name": "New Staff",
        "password": "staffpassword123",
        "role": "admin",
    }
    response = await authenticated_client.post("/api/v1/users", json=user_data)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == user_data["email"]
    assert data["role"] == "admin"


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_create_user_defaults_to_customer(authenticated_client: AsyncClient):
    user_data = {
        "email": f"new_{uuid.uuid4()}@example.com",
        "full_name": "Regular User",
        "password": "password12345",
    }
    response = await authenticated_client.post("/api/v1/users", json=user_data)
    assert response.status_code == 201
    assert response.json()["role"] == "customer"


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_create_user_invalid_role(authenticated_client: AsyncClient):
    user_data = {
        "email": f"new_{uuid.uuid4()}@example.com",
        "full_name": "Bad Role",
        "password": "password12345",
        "role": "superadmin",
    }
    response = await authenticated_client.post("/api/v1/users", json=user_data)
    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_create_user_duplicate_email(authenticated_client: AsyncClient):
    email = f"dupe_{uuid.uuid4()}@example.com"
    user_data = {"email": email, "full_name": "First", "password": "password12345"}
    response1 = await authenticated_client.post("/api/v1/users", json=user_data)
    assert response1.status_code == 201

    response2 = await authenticated_client.post("/api/v1/users", json=user_data)
    assert response2.status_code == 409


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_cannot_create_user(customer_client: AsyncClient):
    user_data = {
        "email": f"new_{uuid.uuid4()}@example.com",
        "full_name": "Sneaky User",
        "password": "password12345",
    }
    response = await customer_client.post("/api/v1/users", json=user_data)
    assert response.status_code == 403


# =============================================================================
# Role promotion / demotion endpoint
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_can_promote_user(
    authenticated_client: AsyncClient, test_customer: DBUser, user_service: UserService
):
    response = await authenticated_client.patch(
        f"/api/v1/users/{test_customer.id}/role", json={"role": "admin"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"

    # Verify in database
    updated = await user_service.retrieve(user_id=test_customer.id)
    assert updated.role == "admin"


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_can_demote_user(authenticated_client: AsyncClient, user_service: UserService):
    # Create an admin user via service, then demote to customer
    from src.routes.v1.users.schema import AdminUserCreateInput

    user = await user_service.create(
        data=AdminUserCreateInput(
            email=f"demote_{uuid.uuid4()}@example.com",
            full_name="To Demote",
            password="password12345",
            role="admin",
        )
    )

    response = await authenticated_client.patch(
        f"/api/v1/users/{user.id}/role", json={"role": "customer"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "customer"


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_promote_invalid_role(authenticated_client: AsyncClient, test_customer: DBUser):
    response = await authenticated_client.patch(
        f"/api/v1/users/{test_customer.id}/role", json={"role": "superadmin"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_promote_nonexistent_user(authenticated_client: AsyncClient):
    response = await authenticated_client.patch(
        f"/api/v1/users/{uuid.uuid4()}/role", json={"role": "admin"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_cannot_promote_user(customer_client: AsyncClient, test_customer: DBUser):
    response = await customer_client.patch(
        f"/api/v1/users/{test_customer.id}/role", json={"role": "admin"}
    )
    assert response.status_code == 403


# =============================================================================
# Admin delete user endpoint
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_can_delete_user(
    authenticated_client: AsyncClient, test_customer: DBUser, user_service: UserService
):
    response = await authenticated_client.delete(f"/api/v1/users/{test_customer.id}")
    assert response.status_code == 204

    # Verify user is gone from database
    with pytest.raises(Exception):
        await user_service.retrieve(user_id=test_customer.id)


@pytest.mark.asyncio(loop_scope="function")
async def test_admin_delete_nonexistent_user(authenticated_client: AsyncClient):
    response = await authenticated_client.delete(f"/api/v1/users/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_cannot_delete_user(customer_client: AsyncClient, test_customer: DBUser):
    response = await customer_client.delete(f"/api/v1/users/{test_customer.id}")
    assert response.status_code == 403


# =============================================================================
# Signup always creates customer (cannot self-assign admin)
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_signup_always_creates_customer(customer_client: AsyncClient):
    signup_data = {
        "email": f"signup_{uuid.uuid4()}@example.com",
        "full_name": "Signup User",
        "password": "password12345",
    }
    response = await customer_client.post("/api/v1/users/signup", json=signup_data)
    assert response.status_code == 201
    assert response.json()["role"] == "customer"


# =============================================================================
# UserOutput includes role field
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_user_output_includes_role(authenticated_client: AsyncClient):
    response = await authenticated_client.get("/api/v1/users/me")
    assert response.status_code == 200
    data = response.json()
    assert "role" in data
    assert data["role"] == "admin"
