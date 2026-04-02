# Draft Technical Notes (Working Document)
> This will be cleaned up into TECHNICAL_COMMENTARY.md for final submission.

## Codebase Assessment (Pre-Implementation)

### Architecture
- 4-layer pattern: Router → Service → Repository → DB
- SQLModel (SQLAlchemy + Pydantic hybrid) for ORM
- FastAPI with async throughout (asyncpg driver)
- Session-based auth: bearer tokens stored in Redis, 30min TTL
- Auth via `authenticate_user` dependency injected into every route
- Tests use dependency override pattern: `app.dependency_overrides[authenticate_user]` to mock auth
- No role/permission concept exists yet — all authenticated users have identical access
- `DBUser` model has: id, email, full_name, hashed_password, is_active, created_at, updated_at
- No `role` or `is_admin` field exists

### Current Endpoint Access Pattern
| Resource | Create | Read (list/get) | Update | Delete |
|----------|--------|-----------------|--------|--------|
| Users    | Public (signup) | Self only (/me) | Self only | Self only (soft delete) |
| Authors  | Any auth user | Any auth user | Any auth user | Any auth user |
| Books    | Any auth user | Any auth user | Any auth user | Any auth user |
| Orders   | Any auth user (own) | Own only | Own only | Own only |

### Key Observations
- Orders are already scoped to the current user (good pattern — user_id from auth, not request body)
- Authors/Books have zero access control beyond "is authenticated"
- The test suite uses an `authenticated_client` fixture that mocks `authenticate_user` to return a `test_user`
- 59 existing tests, all passing

---

## Feature 1: Permissions / RBAC

### Requirements (from README)
- Browsing catalog + placing orders = any customer
- Managing books and authors in catalog = admin only
- "Design and implement a simple permissions model"
- "Decide what operations need protecting, and how permissions are assigned and checked"

### Decisions & Approach

**Decision 1: Role storage — simple `role` field on `DBUser` (Option A)**
- Add `role: str = Field(default="customer")` to `DBUser` with values `"customer"` | `"admin"`
- Why not a separate roles/permissions table (Option B): The README explicitly asks for a "simple permissions model." We have exactly two roles. A many-to-many roles/permissions schema would be over-engineering — adding migration complexity, join overhead, and cognitive load for zero benefit when the domain is binary (customer vs admin). If the permission model needed to grow (e.g., "editor", "moderator", granular per-resource permissions), we'd revisit. For now, YAGNI applies.

**Decision 2: Role assignment — additive approach with admin user creation**
- Default role at signup: `customer` (users cannot self-assign admin)
- Seed an initial admin user during app startup (lifespan handler) so there's always a bootstrap admin
- Admin-only endpoint to promote/demote users: `PATCH /api/v1/users/{user_id}/role`
- Admin-only endpoint to create users with a specified role: `POST /api/v1/users` (separate from public signup)
- This covers the full admin lifecycle: bootstrap (seed) → create users → promote existing users.

  **Why admin user creation (Option B) over promotion-only (Option A):**
  We considered two sub-options for how admins manage users:
  - *Option A (Promotion-only)*: Public signup always creates a customer; admins promote via `PATCH /users/{id}/role`. Simple, one creation path. But requires users to self-register before they can be made admin — admins can't pre-provision accounts.
  - *Option B (Promotion + Admin create-user endpoint)*: Adds `POST /api/v1/users` (admin-only) to create users directly with a specified role, alongside the promotion endpoint.

  We chose Option B because:
  1. It adds minimal complexity (~20-30 lines) — the schema, service, and repository patterns already exist from signup.
  2. It's more production-realistic — admins can pre-provision staff accounts without requiring them to go through public signup.
  3. It demonstrates fuller product thinking — covering the complete admin user management lifecycle rather than the bare minimum.
  4. The README is deliberately ambiguous about admin creation, so going the extra mile shows initiative without over-engineering.

**Decision 3: Permission enforcement — FastAPI dependency injection (Option A)**
- Create a `require_admin` dependency that wraps `authenticate_user` and checks `role == "admin"`
- Swap `Depends(authenticate_user)` → `Depends(require_admin)` on admin-only routes
- Why not decorator-based (Option B): Decorators don't integrate naturally with FastAPI's DI system. You lose automatic OpenAPI docs generation for security requirements, and you fight the framework instead of using it.
- Why not service-layer checks (Option C): This would require threading `current_user` through every service method signature, changing the service interface for a cross-cutting concern. Auth/authz is a transport-layer concern — it belongs at the router/middleware level, not in business logic. The service layer should remain user-agnostic.

**Decision 4: Access control mapping**
| Operation | Access Level | Rationale |
|-----------|-------------|-----------|
| `GET /books`, `GET /books/{id}` | Any authenticated user | Catalog browsing |
| `POST /books`, `PATCH /books/{id}`, `DELETE /books/{id}` | Admin only | Catalog management |
| `GET /authors`, `GET /authors/{id}` | Any authenticated user | Catalog browsing |
| `POST /authors`, `PATCH /authors/{id}`, `DELETE /authors/{id}` | Admin only | Catalog management |
| All order endpoints | Any authenticated user (own orders) | Customer self-service, already user-scoped |
| User endpoints (`/me`) | Any authenticated user (self only) | Unchanged |
| `PATCH /users/{user_id}/role` | Admin only | Role management |
| `POST /users` (admin create) | Admin only | User provisioning |
| All order endpoints | Any authenticated user (own orders) | Unchanged — already user-scoped via auth token. Orders are customer self-service. Admin order oversight (list all orders, change fulfillment status) could be a future enhancement but is out of scope per README. |

**Decision 5: Test strategy — admin-default with customer_client (Option A)**

We evaluated three options for how to adapt the test suite after introducing roles:

- *Option A (Admin default + customer_client)*: Make the existing `test_user` an admin so all 59 tests pass unchanged. Add a new `test_customer` / `customer_client` fixture pair for permission-denial tests.
- *Option B (Customer default + admin_client)*: Keep `test_user` as customer, add `admin_user` / `admin_client`. Update ~32 tests that do write operations on books/authors to use `admin_client`.
- *Option C (Replace authenticated_client entirely)*: Remove `authenticated_client`, create `admin_client` and `customer_client` as peers. Every test explicitly picks one.

We chose Option A because:
1. **Pragmatism over purity**: The existing 59 tests verify CRUD correctness, not permissions. Running them as admin doesn't invalidate their assertions — the role is irrelevant to what they test.
2. **Minimal risk**: Zero changes to working tests. All 59 pass immediately after the role field is added.
3. **Clean new tests**: Permission-specific tests (customer gets 403 on admin routes) use `customer_client` and are purpose-built, making the permission behaviour explicit and easy to review.
4. **Time efficiency**: Under a 4-hour constraint, refactoring 32 test signatures for semantic purity offers no functional benefit. Better to invest that time in a working permission system with proper denial tests.

### Implementation Notes

**What was built:**
- `role` field on `DBUser` (default `"customer"`, indexed)
- `require_admin` FastAPI dependency in `src/utils/auth.py` — 4 lines, chains off existing `authenticate_user`
- Admin seeding in `app_lifespan.py` — idempotent (checks by email before insert), credentials configurable via env vars
- `POST /api/v1/users` — admin creates users with optional role (defaults to customer)
- `PATCH /api/v1/users/{user_id}/role` — admin promotes/demotes, validates role via regex pattern
- `AdminUserCreateInput` and `RoleUpdateInput` schemas with Pydantic regex validation (`^(customer|admin)$`)
- `UserOutput` now includes `role` field
- Updated `UserRepository.create()` type signature to accept `UserSignUpInput | AdminUserCreateInput`
- Books and authors routers: `POST`, `PATCH`, `DELETE` use `Depends(require_admin)`; `GET` stays `Depends(authenticate_user)`

**Test fixture design challenge:**
When both `authenticated_client` (admin) and `customer_client` are used in the same test, they share the same `app.dependency_overrides` dict, which creates a conflict. Initial approach of overriding both `authenticate_user` and `require_admin` in the admin fixture caused the admin override to bleed into customer tests.

Solution: Do NOT override `require_admin` in any fixture. Let FastAPI's DI chain resolve it naturally — `require_admin` depends on `authenticate_user`, which is overridden per-fixture, so the real role check runs against the correct user. For tests needing both admin-created data and customer assertions, we create data via the service layer (bypassing HTTP/auth entirely) and only use `customer_client` for the actual assertion. This cleanly separates "test setup" from "permission testing."

**Test coverage (30 new tests):**
- 6 customer denial tests (3 authors + 3 books: POST/PATCH/DELETE)
- 4 customer access tests (list/get authors, list/get books)
- 6 admin access tests (create/update/delete authors and books)
- 2 customer order tests (create order, list own orders)
- 5 admin user creation tests (success, default role, invalid role, duplicate email, customer denied)
- 5 role promotion tests (promote, demote, invalid role, nonexistent user, customer denied)
- 1 signup role test (always creates customer)
- 1 UserOutput role field test

**Result: 89 tests passing (59 original + 30 new)**

---

## Developer Experience: Smoke Test Script

### Why we added `scripts/smoke_test.py`

The pytest suite (89 tests) mocks authentication via FastAPI's dependency override system — `authenticate_user` is replaced with a function that returns a test user directly, bypassing Redis sessions entirely. This is correct for unit/integration testing but leaves blind spots:

- **Real auth flow never tested**: signup → password hashing → login → Redis session → bearer token → authenticated request
- **Seed admin never verified**: we seed an admin on startup but no automated test confirms it can actually log in
- **Cross-service wiring**: DB ↔ Redis ↔ API working together as deployed

The smoke test script fills this gap by making real HTTP requests to the live Docker stack.

### Why an httpx smoke test script

We needed a way to verify the live API end-to-end beyond the mocked pytest suite. An httpx Python script was the natural choice: httpx is already a project dependency (`pyproject.toml`), Python is the project language, and multi-step flows (login → capture token → use in next request → assert) are trivially expressed in Python compared to shell scripting. The result is a single file that reads like a user story and runs with one command.

### How it works

`just smoke-test` (or `python3 scripts/smoke_test.py`) runs 27 checks across 8 user stories against `http://localhost:8080`:
1. Health check
2. Customer signup → login → profile (real Redis session)
3. Seed admin login (verifies bootstrap worked)
4. Admin creates author + book + updates price
5. Customer browses catalog (read access confirmed)
6. Customer denied all catalog writes (6 × 403)
7. Customer order lifecycle (create → list → view → update)
8. Admin user management (create → promote → demote)

Output is a narrated log — reviewers read it and immediately understand the permission model and user flows without reading code.

### Cleanup and idempotency

The smoke test tracks every resource it creates (users, authors, books, orders) and deletes them in a `finally` block in reverse dependency order (orders → books → authors → users), returning the DB to seed state. This means:
- Running it 10 times doesn't accumulate junk data
- The DB is always in a known state after the test, whether it passed or failed
- This follows the standard test pattern: setup → exercise → verify → **teardown**

To support cleanup, we added `DELETE /api/v1/users/{user_id}` (admin-only, hard delete) — a natural completion of the admin user management story (create, promote, demote, delete).

### Seed module extraction

Moved `seed_admin()` from `app_lifespan.py` to a dedicated `src/utils/seed.py` module. The lifespan handler now only manages infrastructure (DB connections, table creation) and calls `run_all_seeds()`. The seed logic is also callable independently via `just seed` / `scripts/seed.py` for re-seeding after a `db-reset` without restarting the API. This separates infrastructure lifecycle from business data seeding.

