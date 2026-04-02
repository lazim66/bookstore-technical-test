"""Tests for semantic search.

Covers:
- Search returns results ranked by cosine similarity
- Results include relevance scores
- Empty query returns empty results
- Only books with embeddings are searchable
- Search is accessible to any authenticated user (not admin-only)
- Limit parameter validation
- Access control on backfill-embeddings endpoint

Approach: We seed books with manually crafted embedding vectors (not real
OpenAI calls) so we can precisely control similarity relationships. This tests
the search infrastructure — pgvector cosine distance, ranking, filtering, and
response formatting — in isolation from the embedding model's quality.
Real semantic matching quality is verified in the smoke test with live API calls.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession
from src.db.models import DBBook, EMBEDDING_DIMENSIONS
from src.routes.v1.authors.schema import AuthorCreateInput
from src.routes.v1.authors.service import AuthorService


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_vector(seed: float) -> list[float]:
    """Create a simple embedding vector with a dominant dimension.

    Uses a seed value to create vectors that are similar when seeds are
    close together and dissimilar when far apart. This lets us test
    cosine similarity ranking without real embeddings.
    """
    vec = [0.0] * EMBEDDING_DIMENSIONS
    idx = int(abs(seed * 100)) % EMBEDDING_DIMENSIONS
    vec[idx] = 1.0
    # Add a small shared component so no vectors are perfectly orthogonal
    vec[0] = 0.1
    return vec


# Predefined vectors for our test books and queries.
# Books with similar vectors to a query vector will rank higher.
MYSTERY_TOKYO_VEC = _make_vector(1.0)
SCIFI_TIME_VEC = _make_vector(2.0)
COOKBOOK_VEC = _make_vector(3.0)
ROMANCE_VEC = _make_vector(4.0)

# Query vectors — similar to their matching book vectors
QUERY_MYSTERY_VEC = MYSTERY_TOKYO_VEC  # Exact match — highest similarity
QUERY_SCIFI_VEC = SCIFI_TIME_VEC


async def _seed_books_with_embeddings(
    author_service: AuthorService,
    db_session: AsyncSession,
) -> dict[str, uuid.UUID]:
    """Create test books with pre-set embeddings for search testing.

    Returns a dict of book_name → book_id for assertions.
    """
    author = await author_service.create(data=AuthorCreateInput(name="Test Author"))

    books = {
        "mystery": DBBook(
            title="The Tokyo Shadow",
            author_id=author.id,
            description="A gripping debut novel",
            summary="A seasoned detective navigates Tokyo's neon-lit underworld "
            "in this atmospheric mystery. When a series of disappearances in "
            "Shinjuku lead to an underground network, the investigation reveals "
            "dark secrets that threaten to unravel the city's fragile peace.",
            price=19.99,
            embedding=MYSTERY_TOKYO_VEC,
        ),
        "scifi": DBBook(
            title="Chrono Drift",
            author_id=author.id,
            description="An epic saga across centuries",
            summary="In a future where time travel has become commonplace, a "
            "physicist discovers that each jump creates irreversible fractures "
            "in the timeline. As reality begins to unravel, she must race "
            "against the clock to prevent temporal collapse.",
            price=24.99,
            embedding=SCIFI_TIME_VEC,
        ),
        "cookbook": DBBook(
            title="Mountain Flavors",
            author_id=author.id,
            description="Regional recipes from alpine villages",
            summary="A celebration of hearty mountain cuisine, featuring "
            "over 100 recipes passed down through generations of alpine "
            "families. From rustic breads to warming stews, this cookbook "
            "captures the spirit of high-altitude cooking.",
            price=34.99,
            embedding=COOKBOOK_VEC,
        ),
        "romance": DBBook(
            title="Letters from Lisbon",
            author_id=author.id,
            description="A love story spanning decades",
            summary="Two strangers discover a bundle of love letters in a "
            "Lisbon antique shop, setting off a journey through decades of "
            "passion, loss, and rediscovery across Portugal's sun-drenched coast.",
            price=14.99,
            embedding=ROMANCE_VEC,
        ),
        "no_embedding": DBBook(
            title="Unindexed Book",
            author_id=author.id,
            description="This book has no embedding",
            price=9.99,
            embedding=None,
        ),
    }

    ids = {}
    for name, book in books.items():
        await db_session.create(book)
        ids[name] = book.id

    await db_session.commit()
    return ids


# =============================================================================
# Search ranking and relevance
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_search_returns_ranked_results(
    authenticated_client: AsyncClient,
    author_service: AuthorService,
    db_session: AsyncSession,
    _mock_llm_service,
):
    """Search returns results ordered by relevance (most similar first)."""
    book_ids = await _seed_books_with_embeddings(author_service, db_session)

    # Mock: query embedding matches the mystery book vector
    _mock_llm_service.generate_embedding.return_value = QUERY_MYSTERY_VEC

    response = await authenticated_client.get("/api/v1/books/search?q=mystery+novels+set+in+Tokyo")

    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 1

    # The mystery book should rank first (highest similarity)
    assert results[0]["id"] == str(book_ids["mystery"])
    assert results[0]["title"] == "The Tokyo Shadow"
    assert "relevance" in results[0]
    assert results[0]["relevance"] > 0


@pytest.mark.asyncio(loop_scope="function")
async def test_search_scifi_query(
    authenticated_client: AsyncClient,
    author_service: AuthorService,
    db_session: AsyncSession,
    _mock_llm_service,
):
    """Search for sci-fi returns the sci-fi book first."""
    book_ids = await _seed_books_with_embeddings(author_service, db_session)

    _mock_llm_service.generate_embedding.return_value = QUERY_SCIFI_VEC

    response = await authenticated_client.get(
        "/api/v1/books/search?q=science+fiction+about+time+travel"
    )

    assert response.status_code == 200
    results = response.json()
    assert results[0]["id"] == str(book_ids["scifi"])
    assert results[0]["title"] == "Chrono Drift"


@pytest.mark.asyncio(loop_scope="function")
async def test_search_results_exclude_books_without_embeddings(
    authenticated_client: AsyncClient,
    author_service: AuthorService,
    db_session: AsyncSession,
    _mock_llm_service,
):
    """Books without embeddings should not appear in search results."""
    book_ids = await _seed_books_with_embeddings(author_service, db_session)

    _mock_llm_service.generate_embedding.return_value = QUERY_MYSTERY_VEC

    response = await authenticated_client.get("/api/v1/books/search?q=anything")

    assert response.status_code == 200
    result_ids = [r["id"] for r in response.json()]
    assert str(book_ids["no_embedding"]) not in result_ids


@pytest.mark.asyncio(loop_scope="function")
async def test_search_relevance_scores_are_ordered(
    authenticated_client: AsyncClient,
    author_service: AuthorService,
    db_session: AsyncSession,
    _mock_llm_service,
):
    """Relevance scores should be monotonically decreasing in results."""
    await _seed_books_with_embeddings(author_service, db_session)

    _mock_llm_service.generate_embedding.return_value = QUERY_MYSTERY_VEC

    response = await authenticated_client.get("/api/v1/books/search?q=test")

    assert response.status_code == 200
    results = response.json()
    scores = [r["relevance"] for r in results]
    assert scores == sorted(scores, reverse=True), "Results should be ranked by relevance"


# =============================================================================
# Edge cases
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_search_empty_query_returns_empty(authenticated_client: AsyncClient):
    response = await authenticated_client.get("/api/v1/books/search?q=")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio(loop_scope="function")
async def test_search_no_books_returns_empty(
    authenticated_client: AsyncClient,
    _mock_llm_service,
):
    _mock_llm_service.generate_embedding.return_value = [0.0] * EMBEDDING_DIMENSIONS

    response = await authenticated_client.get("/api/v1/books/search?q=anything")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio(loop_scope="function")
async def test_search_respects_limit(
    authenticated_client: AsyncClient,
    author_service: AuthorService,
    db_session: AsyncSession,
    _mock_llm_service,
):
    await _seed_books_with_embeddings(author_service, db_session)

    _mock_llm_service.generate_embedding.return_value = QUERY_MYSTERY_VEC

    response = await authenticated_client.get("/api/v1/books/search?q=test&limit=2")

    assert response.status_code == 200
    assert len(response.json()) == 2


# =============================================================================
# Access control
# =============================================================================


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_can_search(
    customer_client: AsyncClient,
    author_service: AuthorService,
    db_session: AsyncSession,
    _mock_llm_service,
):
    """Search is accessible to any authenticated user, not just admins."""
    await _seed_books_with_embeddings(author_service, db_session)

    _mock_llm_service.generate_embedding.return_value = QUERY_MYSTERY_VEC

    response = await customer_client.get("/api/v1/books/search?q=mystery")
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.asyncio(loop_scope="function")
async def test_search_response_shape(
    authenticated_client: AsyncClient,
    author_service: AuthorService,
    db_session: AsyncSession,
    _mock_llm_service,
):
    """Search results have the expected fields including relevance score."""
    await _seed_books_with_embeddings(author_service, db_session)

    _mock_llm_service.generate_embedding.return_value = QUERY_MYSTERY_VEC

    response = await authenticated_client.get("/api/v1/books/search?q=test")

    assert response.status_code == 200
    result = response.json()[0]
    assert "id" in result
    assert "title" in result
    assert "author_id" in result
    assert "description" in result
    assert "summary" in result
    assert "price" in result
    assert "relevance" in result
    assert isinstance(result["relevance"], float)


@pytest.mark.asyncio(loop_scope="function")
async def test_customer_cannot_backfill_embeddings(customer_client: AsyncClient):
    response = await customer_client.post("/api/v1/books/backfill-embeddings")
    assert response.status_code == 403
