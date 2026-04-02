"""End-to-end smoke tests for the bookstore API.

Exercises the live running API against real Docker containers, testing the
full stack: real HTTP requests, real Redis sessions, real database, and the
seeded admin user.

Unlike pytest unit tests (which mock auth via dependency overrides), this
script validates that the entire system works wired together — the auth flow,
session tokens, permission enforcement, and seeded data.

Cleans up after itself: all resources created during the test are deleted in
a finally block, returning the database to its seed state.

Usage:
    just smoke-test
    # or directly: python3 scripts/smoke_test.py

Prerequisites:
    - API running (`just start`)
    - httpx installed (already a project dependency; `pip install httpx` if
      running outside the container)
"""

import sys
import uuid

import httpx

BASE_URL = "http://localhost:8080"
API_URL = f"{BASE_URL}/api/v1"

# Seed admin credentials (must match .env / settings.py defaults)
SEED_ADMIN_EMAIL = "admin@bookstore.com"
SEED_ADMIN_PASSWORD = "admin123secure"


# ── Output helpers ───────────────────────────────────────────────────────────


class Reporter:
    """Tracks and formats smoke test results."""

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

    def summary(self) -> bool:
        total = self.passed + self.failed
        print(f"\n{'═' * 62}")
        if self.failed == 0:
            print(f"  All {total} checks passed ✓")
        else:
            print(f"  {self.passed}/{total} passed, {self.failed} FAILED ✗")
        print(f"{'═' * 62}\n")
        return self.failed == 0


# ── Cleanup tracker ──────────────────────────────────────────────────────────


class ResourceTracker:
    """Tracks resources created during the smoke test for cleanup.

    Resources are deleted in reverse dependency order:
    orders → books → authors → users
    """

    def __init__(self) -> None:
        self.order_ids: list[str] = []
        self.book_ids: list[str] = []
        self.author_ids: list[str] = []
        self.user_ids: list[str] = []

    def cleanup(self, client: httpx.Client, admin_headers: dict[str, str]) -> None:
        """Delete all tracked resources. Runs in finally block."""
        print("\n── Cleanup: returning DB to seed state ───────────────────────")

        # We need per-user headers for order deletion (orders are user-scoped).
        # But we may not have them if the test failed early. In that case,
        # orders will fail to delete — acceptable, as db-reset is the fallback.
        for oid in self.order_ids:
            # Orders are owned by the customer, but admin can't delete others'
            # orders via the current API. Skip order cleanup if we don't have
            # customer headers — the user will be deleted anyway, and in a real
            # system orphan cleanup would handle this.
            pass

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


# ── API client helper ────────────────────────────────────────────────────────


def login(client: httpx.Client, email: str, password: str) -> dict[str, str]:
    """Authenticate and return bearer token headers."""
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
    """Customer signs up, logs in, and views their profile."""
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
    """The seeded admin can log in and has the admin role."""
    _r.header("Admin: seed admin login")

    r = client.post(f"{API_URL}/users/login", json={
        "email": SEED_ADMIN_EMAIL, "password": SEED_ADMIN_PASSWORD,
    })
    _r.check("POST", "/users/login", r, 200, "seed admin authenticated")

    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = client.get(f"{API_URL}/users/me", headers=headers)
    _r.check("GET", "/users/me", r, 200, f"role={r.json().get('role')}")

    return headers


def test_admin_catalog_management(
    client: httpx.Client, admin_headers: dict[str, str], tracker: ResourceTracker
) -> tuple[str, str]:
    """Admin creates an author, a book, and updates the book price."""
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
    _r.check("PATCH", f"/books/{book_id}", r, 200, "price updated to $19.99")

    return author_id, book_id


def test_customer_can_browse_catalog(
    client: httpx.Client, customer_headers: dict[str, str], book_id: str
) -> None:
    """Customer can list and view authors and books."""
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
    """Customer is denied all write operations on the catalog."""
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
    """Customer places an order, lists it, views it, and updates quantity."""
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
    """Admin creates a user, promotes to admin, then demotes back."""
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
    """Requests without a token are rejected."""
    _r.header("Unauthenticated: requests rejected")

    r = client.get(f"{API_URL}/books")
    _r.check("GET", "/books", r, 403, "no token")

    r = client.post(f"{API_URL}/orders", json={"book_id": str(uuid.uuid4()), "quantity": 1})
    _r.check("POST", "/orders", r, 403, "no token")


# ── Main ─────────────────────────────────────────────────────────────────────

_r = Reporter()


def main() -> None:
    print("=" * 62)
    print("  Bookstore API — Smoke Test")
    print(f"  Target: {BASE_URL}")
    print("=" * 62)

    client = httpx.Client(timeout=10)
    tracker = ResourceTracker()
    admin_headers: dict[str, str] = {}
    customer_headers: dict[str, str] = {}

    try:
        # 1. Basic connectivity
        test_health(client)

        # 2. Auth flows (real signup → login → Redis session → token)
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

    except httpx.ConnectError:
        print("\n  ✗ Could not connect to API. Is it running? (just start)")
        sys.exit(1)
    finally:
        # Clean up all created resources — even if tests failed mid-run.
        # Orders are deleted by their owning customer; everything else by admin.
        if admin_headers:
            # Delete orders via customer (orders are user-scoped)
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
