"""Tests for user endpoints."""

import uuid
from uuid import UUID

import pytest
from httpx import AsyncClient
from src.db.models import DBUser
from src.routes.v1.users.service import UserService
from src.utils.auth import verify_password


@pytest.mark.asyncio(loop_scope="function")
async def test_signup_success(client: AsyncClient, user_service: UserService):
    signup_data = {
        "email": f"newuser_{uuid.uuid4()}@example.com",
        "full_name": "New Test User",
        "password": "password123",
    }

    response = await client.post("/api/v1/users/signup", json=signup_data)

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == signup_data["email"]
    assert data["full_name"] == signup_data["full_name"]
    assert data["id"] is not None
    assert "password" not in data
    assert "hashed_password" not in data
    assert "is_active" not in data
    assert "created_at" not in data
    assert "updated_at" not in data

    # Verify user was created in database
    created_user = await user_service.retrieve(user_id=UUID(data["id"]))
    assert created_user.email == signup_data["email"]
    assert created_user.full_name == signup_data["full_name"]
    assert created_user.is_active is True
    assert created_user.hashed_password is not None


@pytest.mark.asyncio(loop_scope="function")
async def test_signup_duplicate_email(client: AsyncClient, test_user: DBUser):
    signup_data = {
        "email": test_user.email,
        "full_name": "Duplicate User",
        "password": "password123",
    }

    response = await client.post("/api/v1/users/signup", json=signup_data)

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


@pytest.mark.asyncio(loop_scope="function")
async def test_signup_invalid_password(client: AsyncClient):
    signup_data = {
        "email": f"user_{uuid.uuid4()}@example.com",
        "full_name": "Test User",
        "password": "short",
    }

    response = await client.post("/api/v1/users/signup", json=signup_data)

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="function")
async def test_login_success(client: AsyncClient, test_user: DBUser):
    login_data = {
        "email": test_user.email,
        "password": "testpassword123",
    }

    response = await client.post("/api/v1/users/login", json=login_data)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == test_user.email
    assert data["user"]["id"] == str(test_user.id)
    assert "password" not in data["user"]
    assert "hashed_password" not in data["user"]


@pytest.mark.asyncio(loop_scope="function")
async def test_login_invalid_email(client: AsyncClient):
    login_data = {
        "email": "nonexistent@example.com",
        "password": "password123",
    }

    response = await client.post("/api/v1/users/login", json=login_data)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio(loop_scope="function")
async def test_login_invalid_password(client: AsyncClient, test_user: DBUser):
    login_data = {
        "email": test_user.email,
        "password": "wrongpassword",
    }

    response = await client.post("/api/v1/users/login", json=login_data)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio(loop_scope="function")
async def test_login_inactive_user(client: AsyncClient, test_user: DBUser, user_service: UserService):
    # Deactivate user
    await user_service.delete(user_id=test_user.id)

    login_data = {
        "email": test_user.email,
        "password": "testpassword123",
    }

    response = await client.post("/api/v1/users/login", json=login_data)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio(loop_scope="function")
async def test_get_me_success(authenticated_client: AsyncClient, test_user: DBUser):
    response = await authenticated_client.get("/api/v1/users/me")

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email
    assert data["full_name"] == test_user.full_name
    assert data["id"] == str(test_user.id)
    assert "password" not in data
    assert "hashed_password" not in data
    assert "is_active" not in data
    assert "created_at" not in data
    assert "updated_at" not in data


@pytest.mark.asyncio(loop_scope="function")
async def test_get_me_unauthorized(client: AsyncClient):
    response = await client.get("/api/v1/users/me")

    assert response.status_code == 403


@pytest.mark.asyncio(loop_scope="function")
async def test_update_me_full_name(authenticated_client: AsyncClient, test_user: DBUser, user_service: UserService):
    update_data = {
        "full_name": "Updated Name",
    }

    response = await authenticated_client.patch("/api/v1/users/me", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Updated Name"
    assert data["email"] == test_user.email

    # Verify full name was updated in database
    updated_user = await user_service.retrieve(user_id=test_user.id)
    assert updated_user.full_name == "Updated Name"


@pytest.mark.asyncio(loop_scope="function")
async def test_update_me_password(authenticated_client: AsyncClient, test_user: DBUser, user_service: UserService):
    update_data = {
        "password": "newpassword123",
    }

    response = await authenticated_client.patch("/api/v1/users/me", json=update_data)

    assert response.status_code == 200

    # Verify password was updated in database
    updated_user = await user_service.retrieve(user_id=test_user.id)
    assert verify_password("newpassword123", updated_user.hashed_password)


@pytest.mark.asyncio(loop_scope="function")
async def test_update_me_full_name_and_password(
    authenticated_client: AsyncClient, test_user: DBUser, user_service: UserService
):
    update_data = {
        "full_name": "New Full Name",
        "password": "anotherpassword123",
    }

    response = await authenticated_client.patch("/api/v1/users/me", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "New Full Name"
    assert "password" not in data
    assert "hashed_password" not in data

    # Verify both full name and password were updated in database
    updated_user = await user_service.retrieve(user_id=test_user.id)
    assert updated_user.full_name == "New Full Name"
    assert verify_password("anotherpassword123", updated_user.hashed_password)


@pytest.mark.asyncio(loop_scope="function")
async def test_update_me_no_changes(authenticated_client: AsyncClient):
    update_data = {}

    response = await authenticated_client.patch("/api/v1/users/me", json=update_data)

    assert response.status_code == 200


@pytest.mark.asyncio(loop_scope="function")
async def test_update_me_unauthorized(client: AsyncClient):
    update_data = {
        "full_name": "Should Fail",
    }

    response = await client.patch("/api/v1/users/me", json=update_data)

    assert response.status_code == 403


@pytest.mark.asyncio(loop_scope="function")
async def test_delete_me_success(authenticated_client: AsyncClient, test_user: DBUser, user_service: UserService):
    response = await authenticated_client.delete("/api/v1/users/me")

    assert response.status_code == 204

    # Verify user is inactive in database
    deleted_user = await user_service.retrieve(user_id=test_user.id)
    assert deleted_user.is_active is False


@pytest.mark.asyncio(loop_scope="function")
async def test_delete_me_unauthorized(client: AsyncClient):
    response = await client.delete("/api/v1/users/me")

    assert response.status_code == 403
