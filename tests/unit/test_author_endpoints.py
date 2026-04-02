"""Tests for author endpoints."""

import uuid
from uuid import UUID

import pytest
from httpx import AsyncClient
from src.routes.v1.authors.service import AuthorService


@pytest.mark.asyncio(loop_scope="function")
async def test_create_author_success(authenticated_client: AsyncClient, author_service: AuthorService):
    author_data = {
        "name": "Jane Doe",
        "bio": "A talented writer",
    }

    response = await authenticated_client.post("/api/v1/authors", json=author_data)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == author_data["name"]
    assert data["bio"] == author_data["bio"]
    assert data["id"] is not None

    # Verify author was created in database
    created_author = await author_service.retrieve(author_id=UUID(data["id"]))
    assert created_author.name == author_data["name"]
    assert created_author.bio == author_data["bio"]


@pytest.mark.asyncio(loop_scope="function")
async def test_create_author_without_bio(authenticated_client: AsyncClient, author_service: AuthorService):
    author_data = {
        "name": "John Smith",
    }

    response = await authenticated_client.post("/api/v1/authors", json=author_data)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == author_data["name"]
    assert data["bio"] is None


@pytest.mark.asyncio(loop_scope="function")
async def test_create_author_invalid_name(authenticated_client: AsyncClient):
    author_data = {
        "name": "",
        "bio": "Some bio",
    }

    response = await authenticated_client.post("/api/v1/authors", json=author_data)

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="function")
async def test_list_authors_empty(authenticated_client: AsyncClient):
    response = await authenticated_client.get("/api/v1/authors")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio(loop_scope="function")
async def test_list_authors_with_data(authenticated_client: AsyncClient):
    # Create test authors via API
    author1_data = {"name": "Author One", "bio": "Bio one"}
    author2_data = {"name": "Author Two"}

    response1 = await authenticated_client.post("/api/v1/authors", json=author1_data)
    assert response1.status_code == 201
    author1 = response1.json()

    response2 = await authenticated_client.post("/api/v1/authors", json=author2_data)
    assert response2.status_code == 201
    author2 = response2.json()

    response = await authenticated_client.get("/api/v1/authors")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert any(a["id"] == author1["id"] for a in data)
    assert any(a["id"] == author2["id"] for a in data)


@pytest.mark.asyncio(loop_scope="function")
async def test_get_author_success(authenticated_client: AsyncClient):
    # Create test author via API
    author_data = {"name": "Test Author", "bio": "Test bio"}
    create_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert create_response.status_code == 201
    created_author = create_response.json()

    response = await authenticated_client.get(f"/api/v1/authors/{created_author['id']}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created_author["id"]
    assert data["name"] == "Test Author"
    assert data["bio"] == "Test bio"


@pytest.mark.asyncio(loop_scope="function")
async def test_get_author_not_found(authenticated_client: AsyncClient):
    random_id = uuid.uuid4()
    response = await authenticated_client.get(f"/api/v1/authors/{random_id}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio(loop_scope="function")
async def test_update_author_name(authenticated_client: AsyncClient, author_service: AuthorService):
    # Create test author via API
    author_data = {"name": "Original Name", "bio": "Original bio"}
    create_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert create_response.status_code == 201
    created_author = create_response.json()

    update_data = {
        "name": "Updated Name",
    }

    response = await authenticated_client.patch(f"/api/v1/authors/{created_author['id']}", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["bio"] == "Original bio"

    # Verify name was updated in database
    updated_author = await author_service.retrieve(author_id=UUID(created_author["id"]))
    assert updated_author.name == "Updated Name"


@pytest.mark.asyncio(loop_scope="function")
async def test_update_author_bio(authenticated_client: AsyncClient, author_service: AuthorService):
    # Create test author via API
    author_data = {"name": "Author Name", "bio": "Old bio"}
    create_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert create_response.status_code == 201
    created_author = create_response.json()

    update_data = {
        "bio": "New bio",
    }

    response = await authenticated_client.patch(f"/api/v1/authors/{created_author['id']}", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Author Name"
    assert data["bio"] == "New bio"

    # Verify bio was updated in database
    updated_author = await author_service.retrieve(author_id=UUID(created_author["id"]))
    assert updated_author.bio == "New bio"


@pytest.mark.asyncio(loop_scope="function")
async def test_update_author_not_found(authenticated_client: AsyncClient):
    random_id = uuid.uuid4()
    update_data = {
        "name": "New Name",
    }

    response = await authenticated_client.patch(f"/api/v1/authors/{random_id}", json=update_data)

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="function")
async def test_delete_author_success(authenticated_client: AsyncClient, author_service: AuthorService):
    # Create test author via API
    author_data = {"name": "To Delete", "bio": "Will be deleted"}
    create_response = await authenticated_client.post("/api/v1/authors", json=author_data)
    assert create_response.status_code == 201
    created_author = create_response.json()

    response = await authenticated_client.delete(f"/api/v1/authors/{created_author['id']}")

    assert response.status_code == 204

    # Verify author was deleted from database
    with pytest.raises(Exception):
        await author_service.retrieve(author_id=UUID(created_author["id"]))


@pytest.mark.asyncio(loop_scope="function")
async def test_delete_author_not_found(authenticated_client: AsyncClient):
    random_id = uuid.uuid4()
    response = await authenticated_client.delete(f"/api/v1/authors/{random_id}")

    assert response.status_code == 404
