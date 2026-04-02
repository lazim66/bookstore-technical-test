"""Tests for order endpoints."""

import uuid
from uuid import UUID

import pytest
from httpx import AsyncClient
from src.routes.v1.orders.service import OrderService


@pytest.mark.asyncio(loop_scope="function")
async def test_create_order_success(authenticated_client: AsyncClient, order_service: OrderService, test_user):
    # Create test author via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    # Create test book via API
    book_data = {"title": "Test Book", "author_id": author["id"], "price": 19.99}
    book_response = await authenticated_client.post("/api/v1/books", json=book_data)
    assert book_response.status_code == 201
    book = book_response.json()

    order_data = {
        "book_id": book["id"],
        "quantity": 2,
    }

    response = await authenticated_client.post("/api/v1/orders", json=order_data)

    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == str(test_user.id)
    assert data["book_id"] == book["id"]
    assert data["quantity"] == 2
    assert data["total_amount"] == 39.98
    assert data["status"] == "pending"
    assert data["id"] is not None

    # Verify order was created in database
    created_order = await order_service.retrieve(order_id=UUID(data["id"]))
    assert created_order.user_id == test_user.id
    assert str(created_order.book_id) == book["id"]
    assert created_order.quantity == 2


@pytest.mark.asyncio(loop_scope="function")
async def test_create_order_default_quantity(authenticated_client: AsyncClient, test_user):
    # Create test author via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    # Create test book via API
    book_data = {"title": "Test Book", "author_id": author["id"], "price": 19.99}
    book_response = await authenticated_client.post("/api/v1/books", json=book_data)
    assert book_response.status_code == 201
    book = book_response.json()

    order_data = {
        "book_id": book["id"],
    }

    response = await authenticated_client.post("/api/v1/orders", json=order_data)

    assert response.status_code == 201
    data = response.json()
    assert data["quantity"] == 1
    assert data["total_amount"] == 19.99


@pytest.mark.asyncio(loop_scope="function")
async def test_create_order_invalid_quantity(authenticated_client: AsyncClient, test_user):
    # Create test author via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    # Create test book via API
    book_data = {"title": "Test Book", "author_id": author["id"], "price": 19.99}
    book_response = await authenticated_client.post("/api/v1/books", json=book_data)
    assert book_response.status_code == 201
    book = book_response.json()

    order_data = {
        "book_id": book["id"],
        "quantity": 0,
    }

    response = await authenticated_client.post("/api/v1/orders", json=order_data)

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="function")
async def test_create_order_book_not_found(authenticated_client: AsyncClient, test_user):
    order_data = {
        "book_id": str(uuid.uuid4()),
        "quantity": 1,
    }

    response = await authenticated_client.post("/api/v1/orders", json=order_data)

    assert response.status_code == 404
    assert "book" in response.json()["detail"].lower()


@pytest.mark.asyncio(loop_scope="function")
async def test_list_orders_empty(authenticated_client: AsyncClient):
    response = await authenticated_client.get("/api/v1/orders")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio(loop_scope="function")
async def test_list_orders_with_data(authenticated_client: AsyncClient):
    # Create test author via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    # Create test book via API
    book_data = {"title": "Test Book", "author_id": author["id"], "price": 19.99}
    book_response = await authenticated_client.post("/api/v1/books", json=book_data)
    assert book_response.status_code == 201
    book = book_response.json()

    # Create test orders via API
    order1_data = {"book_id": book["id"], "quantity": 1}
    order1_response = await authenticated_client.post("/api/v1/orders", json=order1_data)
    assert order1_response.status_code == 201
    order1 = order1_response.json()

    order2_data = {"book_id": book["id"], "quantity": 2}
    order2_response = await authenticated_client.post("/api/v1/orders", json=order2_data)
    assert order2_response.status_code == 201
    order2 = order2_response.json()

    response = await authenticated_client.get("/api/v1/orders")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert any(o["id"] == order1["id"] for o in data)
    assert any(o["id"] == order2["id"] for o in data)


@pytest.mark.asyncio(loop_scope="function")
async def test_get_order_success(authenticated_client: AsyncClient, test_user):
    # Create test author via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    # Create test book via API
    book_data = {"title": "Test Book", "author_id": author["id"], "price": 19.99}
    book_response = await authenticated_client.post("/api/v1/books", json=book_data)
    assert book_response.status_code == 201
    book = book_response.json()

    # Create test order via API
    order_data = {"book_id": book["id"], "quantity": 3}
    create_response = await authenticated_client.post("/api/v1/orders", json=order_data)
    assert create_response.status_code == 201
    created_order = create_response.json()

    response = await authenticated_client.get(f"/api/v1/orders/{created_order['id']}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created_order["id"]
    assert data["user_id"] == str(test_user.id)
    assert data["book_id"] == book["id"]
    assert data["quantity"] == 3
    assert data["total_amount"] == 59.97
    assert data["status"] == "pending"


@pytest.mark.asyncio(loop_scope="function")
async def test_get_order_not_found(authenticated_client: AsyncClient):
    random_id = uuid.uuid4()
    response = await authenticated_client.get(f"/api/v1/orders/{random_id}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio(loop_scope="function")
async def test_update_order_quantity(authenticated_client: AsyncClient, order_service: OrderService):
    # Create test author via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    # Create test book via API
    book_data = {"title": "Test Book", "author_id": author["id"], "price": 19.99}
    book_response = await authenticated_client.post("/api/v1/books", json=book_data)
    assert book_response.status_code == 201
    book = book_response.json()

    # Create test order via API
    order_data = {"book_id": book["id"], "quantity": 1}
    create_response = await authenticated_client.post("/api/v1/orders", json=order_data)
    assert create_response.status_code == 201
    created_order = create_response.json()

    update_data = {
        "quantity": 5,
    }

    response = await authenticated_client.patch(f"/api/v1/orders/{created_order['id']}", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 5
    assert data["total_amount"] == 99.95

    # Verify quantity was updated in database
    updated_order = await order_service.retrieve(order_id=UUID(created_order["id"]))
    assert updated_order.quantity == 5


@pytest.mark.asyncio(loop_scope="function")
async def test_update_order_status(authenticated_client: AsyncClient, order_service: OrderService):
    # Create test author via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    # Create test book via API
    book_data = {"title": "Test Book", "author_id": author["id"], "price": 19.99}
    book_response = await authenticated_client.post("/api/v1/books", json=book_data)
    assert book_response.status_code == 201
    book = book_response.json()

    # Create test order via API
    order_data = {"book_id": book["id"], "quantity": 1}
    create_response = await authenticated_client.post("/api/v1/orders", json=order_data)
    assert create_response.status_code == 201
    created_order = create_response.json()

    update_data = {
        "status": "completed",
    }

    response = await authenticated_client.patch(f"/api/v1/orders/{created_order['id']}", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"

    # Verify status was updated in database
    updated_order = await order_service.retrieve(order_id=UUID(created_order["id"]))
    assert updated_order.status == "completed"


@pytest.mark.asyncio(loop_scope="function")
async def test_update_order_invalid_quantity(authenticated_client: AsyncClient):
    # Create test author via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    # Create test book via API
    book_data = {"title": "Test Book", "author_id": author["id"], "price": 19.99}
    book_response = await authenticated_client.post("/api/v1/books", json=book_data)
    assert book_response.status_code == 201
    book = book_response.json()

    # Create test order via API
    order_data = {"book_id": book["id"], "quantity": 1}
    create_response = await authenticated_client.post("/api/v1/orders", json=order_data)
    assert create_response.status_code == 201
    created_order = create_response.json()

    update_data = {
        "quantity": -1,
    }

    response = await authenticated_client.patch(f"/api/v1/orders/{created_order['id']}", json=update_data)

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="function")
async def test_update_order_not_found(authenticated_client: AsyncClient):
    random_id = uuid.uuid4()
    update_data = {
        "quantity": 5,
    }

    response = await authenticated_client.patch(f"/api/v1/orders/{random_id}", json=update_data)

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="function")
async def test_delete_order_success(authenticated_client: AsyncClient, order_service: OrderService):
    # Create test author via API
    author_data = {"name": "Test Author"}
    author_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert author_response.status_code == 201
    author = author_response.json()

    # Create test book via API
    book_data = {"title": "Test Book", "author_id": author["id"], "price": 19.99}
    book_response = await authenticated_client.post("/api/v1/books", json=book_data)
    assert book_response.status_code == 201
    book = book_response.json()

    # Create test order via API
    order_data = {"book_id": book["id"], "quantity": 1}
    create_response = await authenticated_client.post("/api/v1/orders", json=order_data)
    assert create_response.status_code == 201
    created_order = create_response.json()

    response = await authenticated_client.delete(f"/api/v1/orders/{created_order['id']}")

    assert response.status_code == 204

    # Verify order was deleted from database
    with pytest.raises(Exception):
        await order_service.retrieve(order_id=UUID(created_order["id"]))


@pytest.mark.asyncio(loop_scope="function")
async def test_delete_order_not_found(authenticated_client: AsyncClient):
    random_id = uuid.uuid4()
    response = await authenticated_client.delete(f"/api/v1/orders/{random_id}")

    assert response.status_code == 404
