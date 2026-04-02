"""Tests for health check endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint returns OK."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "OK"}
