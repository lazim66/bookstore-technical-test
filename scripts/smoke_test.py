"""End-to-end smoke tests for the bookstore API.

Exercises the live running API against real Docker containers, testing the
full stack: real HTTP requests, real Redis sessions, real database, seeded
admin user, real OpenAI API calls for summary generation and semantic search.

Cleans up after itself: all resources created during the test are deleted in
a finally block, returning the database to its seed state.

Usage:
    just smoke-test
    # or directly: python3 scripts/smoke_test.py

Prerequisites:
    - API running (`just start`)
    - OPENAI_API_KEY set in .env
    - httpx installed (already a project dependency)
"""

import sys
import time
import uuid

import httpx

BASE_URL = "http://localhost:8080"
API_URL = f"{BASE_URL}/api/v1"

SEED_ADMIN_EMAIL = "admin@bookstore.com"
SEED_ADMIN_PASSWORD = "admin123secure"

# Sample book text for testing summary generation. The title ("The Neon Veil")
# and description ("A debut novel") deliberately DON'T mention "mystery",
# "detective", or "Tokyo" — so if semantic search finds this book for
# "mystery novels set in Tokyo", it proves the system works via the
# summary/embedding, not keyword matching.
SAMPLE_BOOK_TEXT = """
Inspector Kenji Tanaka had spent twenty years walking the rain-slicked streets
of Shinjuku, but nothing had prepared him for this case. Three prominent
businessmen had vanished from the Golden Gai district in the span of a week,
leaving behind only cryptic origami cranes at their favourite bars.

As Tanaka delved deeper into Tokyo's neon-lit underworld, he discovered
connections between the missing men that led to a shadowy organisation
operating from beneath the city's famous Shibuya crossing. Each clue
pulled him further into a web of corporate espionage, ancient grudges,
and a conspiracy that threatened to expose the darkest secrets of Japan's
most powerful families.

With time running out and the trail growing cold, Tanaka must confront
his own past while racing to prevent a catastrophe that could reshape
the power dynamics of modern Tokyo forever.
"""

SAMPLE_SCIFI_TEXT = """
Dr. Elena Vasquez had always believed that time was a river — flowing in
one direction, unchangeable, absolute. That was before she discovered the
Chronos field. Hidden in the quantum foam between moments, the field
offered humanity something unprecedented: the ability to step sideways
through time.

But each jump came with a cost. Every traveller who slipped through the
temporal membrane left fractures in their wake — tiny cracks in causality
that slowly widened into gaping wounds in the fabric of reality. Elena's
calculations showed that if the jumps continued at their current rate,
the cumulative damage would reach a critical threshold within six months.

Now Elena faces an impossible choice: shut down the greatest scientific
achievement in human history, or watch as the universe slowly tears
itself apart at the seams.
"""


# ── Output helpers ───────────────────────────────────────────────────────────


class Reporter:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def header(self, title: str) -> None:
        print(f"\n── {title} {'─' * max(1, 58 - len(title))}")

    def check(
        self,
        method: str,
        path: str,
        response: httpx.Response,
        expected: int,
        note: str = "",
    ) -> None:
        status = response.status_code
        ok = status == expected
        mark = "✓" if ok else "✗"
        detail = f" ({note})" if note else ""

        if ok:
            self.passed += 1
            print(f"  {mark} {method} {path} → {status}{detail}")
        else:
            self.failed += 1
            body = response.text[:200] if response.text else ""
            print(f"  {mark} {method} {path} → {status} (expected {expected}){detail}")
            print(f"    Response: {body}")

    def check_condition(self, description: str, condition: bool, detail: str = "") -> None:
        """Assert a non-HTTP condition (e.g., content quality checks)."""
        mark = "✓" if condition else "✗"
        info = f" ({detail})" if detail else ""
        if condition:
            self.passed += 1
            print(f"  {mark} {description}{info}")
        else:
            self.failed += 1
            print(f"  {mark} FAIL: {description}{info}")

    def summary(self) -> bool:
        total = self.passed + self.failed
        print(f"\n{'═' * 62}")
        if self.failed == 0:
            print(f"  All {total} checks passed ✓")
        else:
            print(f"  {self.passed}/{total} passed, {self.failed} FAILED ✗")
        print(f"{'═' * 62}\n")
        return self.failed == 0


class ResourceTracker:
    def __init__(self) -> None:
        self.order_ids: list[str] = []
        self.book_ids: list[str] = []
        self.author_ids: list[str] = []
        self.user_ids: list[str] = []

    def cleanup(self, client: httpx.Client, admin_headers: dict[str, str]) -> None:
        print("\n── Cleanup: returning DB to seed state ───────────────────────")

        for bid in self.book_ids:
            r = client.delete(f"{API_URL}/books/{bid}", headers=admin_headers)
            _log_cleanup("DELETE", f"/books/{bid}", r)

        for aid in self.author_ids:
            r = client.delete(f"{API_URL}/authors/{aid}", headers=admin_headers)
            _log_cleanup("DELETE", f"/authors/{aid}", r)

        for uid in self.user_ids:
            r = client.delete(f"{API_URL}/users/{uid}", headers=admin_headers)
            _log_cleanup("DELETE", f"/users/{uid}", r)

        print("  Cleanup complete — DB should be back to seed state")


def _log_cleanup(method: str, path: str, response: httpx.Response) -> None:
    status = response.status_code
    mark = "✓" if status == 204 else "✗"
    print(f"  {mark} {method} {path} → {status}")


def login(client: httpx.Client, email: str, password: str) -> dict[str, str]:
    r = client.post(f"{API_URL}/users/login", json={"email": email, "password": password})
    token = r.json().get("access_token", "")
    return {"Authorization": f"Bearer {token}"}


# ── Test flows ───────────────────────────────────────────────────────────────


def test_health(client: httpx.Client) -> None:
    _r.header("Health check")
    r = client.get(f"{BASE_URL}/health")
    _r.check("GET", "/health", r, 200)


def test_customer_signup_and_login(
    client: httpx.Client, tracker: ResourceTracker
) -> dict[str, str]:
    _r.header("Customer: signup → login → profile")

    email = f"smoke_customer_{uuid.uuid4().hex[:8]}@test.com"
    password = "smokepassword123"

    r = client.post(f"{API_URL}/users/signup", json={
        "email": email, "full_name": "Smoke Customer", "password": password,
    })
    _r.check("POST", "/users/signup", r, 201)
    if r.status_code == 201:
        tracker.user_ids.append(r.json()["id"])

    r = client.post(f"{API_URL}/users/login", json={"email": email, "password": password})
    _r.check("POST", "/users/login", r, 200, "token received")

    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = client.get(f"{API_URL}/users/me", headers=headers)
    _r.check("GET", "/users/me", r, 200, f"role={r.json().get('role')}")

    return headers


def test_seed_admin_login(client: httpx.Client) -> dict[str, str]:
    _r.header("Admin: seed admin login")

    r = client.post(f"{API_URL}/users/login", json={
        "email": SEED_ADMIN_EMAIL, "password": SEED_ADMIN_PASSWORD,
    })
    _r.check("POST", "/users/login", r, 200, "seed admin authenticated")

    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return headers


def test_admin_catalog_management(
    client: httpx.Client, admin_headers: dict[str, str], tracker: ResourceTracker
) -> tuple[str, str]:
    _r.header("Admin: catalog management (create author, book, update price)")

    r = client.post(f"{API_URL}/authors", headers=admin_headers, json={
        "name": "Smoke Test Author", "bio": "Written by a smoke test",
    })
    _r.check("POST", "/authors", r, 201)
    author_id = r.json()["id"]
    tracker.author_ids.append(author_id)

    r = client.post(f"{API_URL}/books", headers=admin_headers, json={
        "title": "The Smoke Test", "author_id": author_id,
        "description": "A book about testing", "price": 24.99,
    })
    _r.check("POST", "/books", r, 201)
    book_id = r.json()["id"]
    tracker.book_ids.append(book_id)

    r = client.patch(f"{API_URL}/books/{book_id}", headers=admin_headers, json={
        "price": 19.99,
    })
    _r.check("PATCH", f"/books/{book_id}", r, 200, "price updated")

    return author_id, book_id


def test_admin_creates_books_with_text(
    client: httpx.Client,
    admin_headers: dict[str, str],
    author_id: str,
    tracker: ResourceTracker,
) -> tuple[str, str]:
    """Create two books with full_text for LLM feature testing.

    Titles and descriptions deliberately omit search-relevant keywords
    so semantic search must work via summaries/embeddings, not keywords.
    Returns (mystery_book_id, scifi_book_id).
    """
    _r.header("Admin: create books with full_text for LLM features")

    r = client.post(f"{API_URL}/books", headers=admin_headers, json={
        "title": "The Neon Veil",
        "author_id": author_id,
        "description": "A debut novel",
        "full_text": SAMPLE_BOOK_TEXT,
        "price": 19.99,
    })
    _r.check("POST", "/books", r, 201, "mystery book — title has no mystery/Tokyo keywords")
    mystery_id = r.json()["id"]
    tracker.book_ids.append(mystery_id)

    r = client.post(f"{API_URL}/books", headers=admin_headers, json={
        "title": "Chrono Drift",
        "author_id": author_id,
        "description": "An epic saga",
        "full_text": SAMPLE_SCIFI_TEXT,
        "price": 24.99,
    })
    _r.check("POST", "/books", r, 201, "sci-fi book — title has no time travel keywords")
    scifi_id = r.json()["id"]
    tracker.book_ids.append(scifi_id)

    print("    (Titles deliberately omit search keywords to test semantic matching)")

    return mystery_id, scifi_id


def test_customer_can_browse_catalog(
    client: httpx.Client, customer_headers: dict[str, str], book_id: str
) -> None:
    _r.header("Customer: catalog browsing (read-only access)")

    r = client.get(f"{API_URL}/authors", headers=customer_headers)
    _r.check("GET", "/authors", r, 200, f"{len(r.json())} author(s)")

    r = client.get(f"{API_URL}/books", headers=customer_headers)
    _r.check("GET", "/books", r, 200, f"{len(r.json())} book(s)")

    r = client.get(f"{API_URL}/books/{book_id}", headers=customer_headers)
    _r.check("GET", f"/books/{book_id}", r, 200, f"title={r.json().get('title')}")


def test_customer_denied_catalog_writes(
    client: httpx.Client,
    customer_headers: dict[str, str],
    author_id: str,
    book_id: str,
) -> None:
    _r.header("Customer: permission denial on catalog writes (expect 403)")

    for method, path, json_body in [
        ("POST", "/authors", {"name": "Nope"}),
        ("PATCH", f"/authors/{author_id}", {"name": "Nope"}),
        ("DELETE", f"/authors/{author_id}", None),
        ("POST", "/books", {"title": "Nope", "author_id": author_id, "price": 9.99}),
        ("PATCH", f"/books/{book_id}", {"title": "Nope"}),
        ("DELETE", f"/books/{book_id}", None),
    ]:
        r = client.request(method, f"{API_URL}{path}", headers=customer_headers, json=json_body)
        _r.check(method, path, r, 403, "denied")


def test_customer_can_place_and_manage_orders(
    client: httpx.Client,
    customer_headers: dict[str, str],
    book_id: str,
    tracker: ResourceTracker,
) -> None:
    _r.header("Customer: order lifecycle (create → list → view → update)")

    r = client.post(f"{API_URL}/orders", headers=customer_headers, json={
        "book_id": book_id, "quantity": 2,
    })
    _r.check("POST", "/orders", r, 201, f"total=${r.json().get('total_amount')}")
    order_id = r.json()["id"]
    tracker.order_ids.append(order_id)

    r = client.get(f"{API_URL}/orders", headers=customer_headers)
    _r.check("GET", "/orders", r, 200, f"{len(r.json())} order(s)")

    r = client.get(f"{API_URL}/orders/{order_id}", headers=customer_headers)
    _r.check("GET", f"/orders/{order_id}", r, 200, f"status={r.json().get('status')}")

    r = client.patch(f"{API_URL}/orders/{order_id}", headers=customer_headers, json={
        "quantity": 3,
    })
    _r.check("PATCH", f"/orders/{order_id}", r, 200, f"total=${r.json().get('total_amount')}")


def test_admin_user_management(
    client: httpx.Client, admin_headers: dict[str, str], tracker: ResourceTracker
) -> None:
    _r.header("Admin: user management (create → promote → demote)")

    email = f"smoke_staff_{uuid.uuid4().hex[:8]}@test.com"
    r = client.post(f"{API_URL}/users", headers=admin_headers, json={
        "email": email, "full_name": "Staff Member", "password": "staffpass123",
    })
    _r.check("POST", "/users", r, 201, f"role={r.json().get('role')}")
    user_id = r.json()["id"]
    tracker.user_ids.append(user_id)

    r = client.patch(f"{API_URL}/users/{user_id}/role", headers=admin_headers, json={
        "role": "admin",
    })
    _r.check("PATCH", f"/users/{user_id}/role", r, 200, "promoted to admin")

    r = client.patch(f"{API_URL}/users/{user_id}/role", headers=admin_headers, json={
        "role": "customer",
    })
    _r.check("PATCH", f"/users/{user_id}/role", r, 200, "demoted to customer")


def test_unauthenticated_requests_rejected(client: httpx.Client) -> None:
    _r.header("Unauthenticated: requests rejected")

    r = client.get(f"{API_URL}/books")
    _r.check("GET", "/books", r, 403, "no token")

    r = client.post(f"{API_URL}/orders", json={"book_id": str(uuid.uuid4()), "quantity": 1})
    _r.check("POST", "/orders", r, 403, "no token")


# ── LLM Feature Tests ───────────────────────────────────────────────────────


def test_book_summary_generation(
    client: httpx.Client,
    admin_headers: dict[str, str],
    book_id: str,
) -> None:
    """Verify summary is auto-generated in background for a book with full_text."""
    _r.header("Summary: auto-generation for 'The Neon Veil' (real LLM)")
    print("    Source: ~300-word mystery text set in Tokyo's Shinjuku district")

    # Summary is generated in background — poll until it appears
    summary = None
    for attempt in range(15):
        time.sleep(2)
        r = client.get(f"{API_URL}/books/{book_id}", headers=admin_headers)
        summary = r.json().get("summary")
        if summary:
            break

    _r.check_condition(
        "Summary generated via background task",
        summary is not None,
        f"after {(attempt + 1) * 2}s",
    )

    if summary:
        _r.check_condition(
            "Summary is concise (< 500 words)",
            len(summary.split()) < 500,
            f"{len(summary.split())} words",
        )
        _r.check_condition(
            "Summary is substantial (> 30 words)",
            len(summary.split()) > 30,
            f"{len(summary.split())} words",
        )
        print(f"    Generated summary:")
        for line in summary.split("\n"):
            if line.strip():
                print(f"      {line.strip()}")


def test_book_summary_via_summarize_endpoint(
    client: httpx.Client,
    admin_headers: dict[str, str],
    book_id: str,
) -> None:
    """Generate summary via the explicit /summarize endpoint."""
    _r.header("Summary: /summarize endpoint for 'Chrono Drift' (real LLM)")
    print("    Source: ~250-word sci-fi text about time travel and temporal fractures")

    # Wait for any background task to complete first
    time.sleep(5)

    r = client.post(f"{API_URL}/books/{book_id}/summarize", headers=admin_headers)
    _r.check("POST", f"/books/{book_id}/summarize", r, 200, "summary generated synchronously")

    if r.status_code != 200:
        return

    summary = r.json().get("summary", "")
    _r.check_condition(
        "Summary mentions time-related themes",
        any(word in summary.lower() for word in ["time", "temporal", "chronos", "travel", "jump"]),
        "content relevant to source text",
    )
    print(f"    Generated summary:")
    for line in summary.split("\n"):
        if line.strip():
            print(f"      {line.strip()}")


def test_semantic_search(
    client: httpx.Client,
    customer_headers: dict[str, str],
    mystery_book_id: str,
    scifi_book_id: str,
) -> None:
    """Test semantic search with the README's example queries.

    The key test: titles and descriptions do NOT contain the search terms.
    "The Neon Veil" (description: "A debut novel") should match
    "mystery novels set in Tokyo" via the summary and embedding.
    """
    _r.header("Search: semantic search with natural language (real embeddings)")
    print("    Testing README examples — titles don't contain search keywords")

    # Test 1: "mystery novels set in Tokyo"
    r = client.get(
        f"{API_URL}/books/search",
        params={"q": "mystery novels set in Tokyo"},
        headers=customer_headers,
    )
    _r.check("GET", "/books/search?q=mystery+novels+set+in+Tokyo", r, 200)
    results = r.json()

    _r.check_condition(
        "Search returns results",
        len(results) > 0,
        f"{len(results)} result(s)",
    )

    if results:
        _r.check_condition(
            "Mystery book ranks first for 'mystery novels set in Tokyo'",
            results[0]["id"] == mystery_book_id,
            f"top result: {results[0].get('title')}",
        )
        _r.check_condition(
            "Results include relevance scores",
            "relevance" in results[0] and results[0]["relevance"] > 0,
            f"score={results[0].get('relevance')}",
        )

    # Test 2: "science fiction about time travel"
    r = client.get(
        f"{API_URL}/books/search",
        params={"q": "science fiction about time travel"},
        headers=customer_headers,
    )
    _r.check("GET", "/books/search?q=science+fiction+about+time+travel", r, 200)
    results = r.json()

    if results:
        _r.check_condition(
            "Sci-fi book ranks first for 'science fiction about time travel'",
            results[0]["id"] == scifi_book_id,
            f"top result: {results[0].get('title')}",
        )

    # Test 3: Results are ranked by relevance (scores descending)
    if len(results) > 1:
        scores = [r["relevance"] for r in results]
        _r.check_condition(
            "Results ranked by relevance (descending scores)",
            scores == sorted(scores, reverse=True),
        )

    # Test 4: Search works even though exact words aren't in title/description
    # "The Neon Veil" title doesn't contain "mystery" or "Tokyo"
    # "Chrono Drift" title doesn't contain "science fiction" or "time travel"
    r = client.get(
        f"{API_URL}/books/search",
        params={"q": "detective investigating disappearances in Japan"},
        headers=customer_headers,
    )
    _r.check("GET", "/books/search?q=detective+investigating+in+Japan", r, 200)
    results = r.json()

    if results:
        _r.check_condition(
            "Finds relevant book via semantic meaning (not keyword match)",
            results[0]["id"] == mystery_book_id,
            f"top result: {results[0].get('title')}",
        )


# ── Main ─────────────────────────────────────────────────────────────────────

_r = Reporter()


def main() -> None:
    print("=" * 62)
    print("  Bookstore API — Smoke Test")
    print(f"  Target: {BASE_URL}")
    print("=" * 62)

    client = httpx.Client(timeout=30)  # Higher timeout for LLM calls
    tracker = ResourceTracker()
    admin_headers: dict[str, str] = {}
    customer_headers: dict[str, str] = {}

    try:
        # 1. Basic connectivity
        test_health(client)

        # 2. Auth flows
        customer_headers = test_customer_signup_and_login(client, tracker)
        admin_headers = test_seed_admin_login(client)

        # 3. Admin manages catalog
        author_id, book_id = test_admin_catalog_management(client, admin_headers, tracker)

        # 4. Customer browses catalog
        test_customer_can_browse_catalog(client, customer_headers, book_id)

        # 5. Customer denied write access
        test_customer_denied_catalog_writes(client, customer_headers, author_id, book_id)

        # 6. Customer order lifecycle
        test_customer_can_place_and_manage_orders(client, customer_headers, book_id, tracker)

        # 7. Admin user management
        test_admin_user_management(client, admin_headers, tracker)

        # 8. Unauthenticated access
        test_unauthenticated_requests_rejected(client)

        # 9. Create books with full_text for LLM testing
        mystery_book_id, scifi_book_id = test_admin_creates_books_with_text(
            client, admin_headers, author_id, tracker,
        )

        # 10. Summary generation (real OpenAI calls)
        test_book_summary_generation(client, admin_headers, mystery_book_id)
        test_book_summary_via_summarize_endpoint(client, admin_headers, scifi_book_id)

        # 11. Semantic search (real embeddings)
        test_semantic_search(client, customer_headers, mystery_book_id, scifi_book_id)

    except httpx.ConnectError:
        print("\n  ✗ Could not connect to API. Is it running? (just start)")
        sys.exit(1)
    finally:
        if admin_headers:
            for oid in tracker.order_ids:
                if customer_headers:
                    client.delete(f"{API_URL}/orders/{oid}", headers=customer_headers)
            tracker.order_ids.clear()
            tracker.cleanup(client, admin_headers)

        client.close()

    success = _r.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
