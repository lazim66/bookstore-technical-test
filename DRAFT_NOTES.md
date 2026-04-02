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

---

## Feature 2: Book Summaries

### Requirements (from README)
- Books need summaries to help customers decide what to read
- When admins add books with full book text, the system should automatically generate customer-friendly summaries using an LLM
- A backfill operation for books added before this feature existed — admin-triggered, processes multiple books
- The system needs to handle many books being added or summarized concurrently

### Decisions & Approach

**Decision 1: Schema changes — add `full_text` and `summary` to `DBBook`**
- `full_text: str | None` — the complete book text, provided by admins when creating/updating a book
- `summary: str | None` — the LLM-generated summary, also editable by admins via `PATCH /books/{id}`
- Summaries are auto-generated but admin-editable. The README says "automatically generate" but allowing admin overrides is zero-cost (the field is already on the update schema) and is pragmatically useful — admins may want to tweak a generated summary for tone or accuracy.

**Decision 2: LLM model selection — GPT-5.4 Nano via OpenAI**
- Summarization is a straightforward task that doesn't need frontier-model intelligence. We chose GPT-5.4 Nano because it offers an excellent cost-to-capability ratio: $0.20/M input tokens, a 400K context window (comfortably handles full book texts in a single pass), and is OpenAI's latest-generation model optimised for tasks like classification and data extraction — which summarization falls under. Compared to larger models in the GPT-5.4 family or alternatives like Claude Haiku, it's significantly cheaper while being more than sufficient for our needs.
- The model is configurable via `OPENAI_MODEL` env var so it can be swapped without code changes.
- We use a simple LLM service abstraction — just enough to keep the OpenAI SDK details out of business logic and make testing straightforward via dependency injection.

**Decision 3: Generation timing — FastAPI BackgroundTasks (async, non-blocking)**
- When an admin creates a book with `full_text`, the API returns 201 immediately, and summary generation runs as a background task
- Why not synchronous (inline): LLM calls take 5-15 seconds. Blocking the request degrades admin UX and risks timeouts. The admin doesn't need to see the summary immediately — they just need confirmation the book was created.
- Why not Celery/task queue: Adds infrastructure complexity (worker process, broker config, serialization) that's disproportionate for this use case. For a production system with retry guarantees and distributed processing, Celery would be the right choice — we note this as a future improvement. BackgroundTasks is the right level of complexity for this scope.
- Trade-off acknowledged: BackgroundTasks are not persistent — if the server crashes mid-generation, the task is lost. The backfill endpoint serves as a recovery mechanism (re-trigger summaries for books that still lack them).

**Decision 4: Concurrency control — `asyncio.Semaphore` with configurable limit**
- When many books are backfilled simultaneously, we limit concurrent LLM API calls using an `asyncio.Semaphore`
- The limit is configurable via `LLM_MAX_CONCURRENT_REQUESTS` env var (default: 5), allowing tuning per environment (higher in production with better rate limits, lower in dev)
- How it works: `asyncio.gather` fires all backfill tasks concurrently, but each task must acquire the semaphore before making an LLM call. At most N calls run simultaneously; the rest queue up. This prevents rate-limit errors and resource exhaustion without sacrificing throughput.
- Why not `asyncio.Queue` with workers: More complex (producer-consumer pattern) for the same result. Semaphore is the standard, minimal pattern for "limit concurrent access to an external resource."
- Why not no control: Firing 50+ simultaneous LLM API calls would hit provider rate limits, cause 429 errors, and potentially exhaust connection pools.

**Decision 5: API design — per-book + batch backfill endpoints**
- `POST /api/v1/books/{id}/summarize` (admin-only): Trigger summary generation for a single book. Useful for re-generating a stale or poor-quality summary, or after updating a book's `full_text`.
- `POST /api/v1/books/backfill-summaries` (admin-only): Trigger summary generation for all books that have `full_text` but no `summary`. Returns the count of books queued. This is the concurrency showcase — the semaphore controls parallel LLM calls.
- The per-book endpoint is the atomic operation; the backfill endpoint composes it across multiple books. This keeps the code DRY and gives admins granular control.

**Decision 6: Testing strategy**
- **Unit tests (mocked LLM)**: The LLM service is injected via FastAPI's dependency system. Tests override it with an `AsyncMock` that returns a canned summary. This tests the full flow (create book → background task → summary populated) without real API calls.
- **Concurrency test**: Fire N concurrent summary requests with a mock that includes a small `asyncio.sleep` delay. Track concurrent execution via a counter to verify the semaphore limits parallelism to the configured max. This directly tests the README's concurrency requirement.
- **Smoke test**: One real LLM call for a single book to verify the API key, model, and prompt work end-to-end against the live stack.

### Implementation Lessons

**Session isolation shaped the architecture.** Our initial design had the `SummaryService` using `managed_session()` directly for all DB operations. This worked in production but broke in tests — the test session creates data within an uncommitted transaction, and the summary service's independent sessions couldn't see it. This forced a cleaner design: the service accepts an injectable session factory, and we split the API into two modes — `generate_summary_text()` (pure LLM call, caller manages DB) for synchronous endpoints, and `generate_for_book()` (owns its DB session) for background tasks and concurrent backfill. The result is actually better separated than the original design.

**Code review caught `full_text` leaking in list responses.** The initial `BookOutput` included `full_text`, which would serialise potentially large book texts for every item in list responses. We split into `BookOutput` (for lists) and `BookDetailOutput` (for single-book retrieval). A good reminder that response schemas should be designed from the consumer's perspective, not just the data model.

### Post-review fixes (permissions feature)

A second code review pass across the permissions code caught three issues worth addressing:
- **Role type safety**: Replaced regex-based role validation (`pattern="^(customer|admin)$"`) with `Literal["customer", "admin"]` on all Pydantic schemas. This gives better IDE support, clearer error messages, and type-level enforcement. The DB model remains `str` due to a SQLModel limitation with `Literal`, but validation at the API boundary is what matters.
- **Self-protection guard**: Added checks preventing admins from deleting their own account or changing their own role — otherwise an admin could accidentally lock out all admin access.
- **Signup role injection test**: Added a test that explicitly passes `"role": "admin"` in a signup payload and verifies it's ignored, ensuring users cannot self-assign admin privileges.

---

## Feature 3: Semantic Search

### Requirements (from README)
- Customers find books using natural language (not exact keyword matches)
- Example queries: "mystery novels set in Tokyo", "science fiction about time travel"
- Relevant results even if exact words don't appear in titles or descriptions
- Results ranked by relevance
- pgvector extension available in the database

### Decisions & Approach

**Summary length control (refinement from Feature 2):**
- Tightened the LLM prompt to specify "150-250 words" explicitly, and reduced `max_tokens` from 1024 to 512. The prompt instruction controls the actual length; `max_tokens` acts as a safety net preventing runaway output while leaving enough headroom (~370 words) to avoid mid-sentence truncation. Keeping summaries concise also benefits embeddings — shorter, focused text produces less semantic dilution in the vector.

**Decision 1: Vector storage — pgvector with HNSW index**
- Add an `embedding` column to `DBBook` using pgvector's `VECTOR(1536)` type
- Use an HNSW index with cosine distance for approximate nearest-neighbour search
- HNSW chosen over IVFFlat because it can be created on an empty table (no training step), has better query performance, and is the recommended default for datasets under millions of rows

**Decision 2: Embedding model — `text-embedding-3-small`**
- Both `text-embedding-3-small` (1536 dims) and `text-embedding-3-large` (3072 dims) support 8,191 input tokens — more than enough for our use case since we're embedding short text (title + description + summary, ~200-500 tokens)
- We chose `text-embedding-3-small` because for short embedded texts, the quality difference is negligible, while it costs 6.5x less ($0.02/M vs $0.13/M tokens) and uses half the storage per vector
- Configurable via `OPENAI_EMBEDDING_MODEL` env var

**Decision 3: What to embed — title + description + summary**
- We considered three options:
  - *Title + description only*: Thin semantic signal. A book titled "The Tokyo Shadow" with description "A gripping novel" would barely match "mystery novels set in Tokyo."
  - *Title + description + summary*: The LLM-generated summary captures themes, genre, setting, and tone — exactly what customers search by. A summary mentioning "detective navigates Tokyo's underworld in this atmospheric mystery" gives the embedding strong signal for mystery + Tokyo + detective queries.
  - *Full book text with chunking*: Both embedding models max out at 8,191 tokens (~6,000 words), while novels are 60,000-100,000+ words. This would require splitting books into hundreds of chunks, storing multiple vectors per book, and aggregating results — a full RAG pipeline that's disproportionate for a bookstore search feature. Research also confirms that "embedding a large, multi-topic text into a single vector dilutes its meaning."
- We chose title + description + summary because the summary is a semantic compression of the entire book into 2-3 paragraphs, purpose-built for discovery. Including AI-generated content in embeddings is no different from indexing a human-written book blurb — it's a condensed representation of the book's content optimised for matching customer intent.

**Decision 4: When to generate embeddings — chained with summary generation**
- This decision is tightly coupled with Decision 3: since the embedding includes the summary, the embedding should be generated after the summary exists.
- We considered two approaches:
  - *Approach A (chosen): Chain embedding after summary in the background task.* When a book is created with full_text, the background task generates the summary, then generates the embedding (title + desc + summary) in sequence. For books without full_text, the embedding is generated synchronously (title + desc only). On book updates, the embedding is regenerated synchronously.
  - *Approach B: Generate embedding synchronously on create (without summary), then regenerate after summary arrives.* This creates two embedding generations per book, doubles the cost, and adds a "progressively improving embedding" state that's harder to reason about.
- We chose Approach A for simplicity and consistency: one code path per scenario, the embedding always reflects the latest state, and the system is predictable. The trade-off — books with full_text aren't searchable for ~10 seconds while the background task runs — is acceptable because admins don't expect instant search availability.

| Trigger | Summary | Embedding | Timing |
|---------|---------|-----------|--------|
| Create book **with** full_text | Generate | Generate (title + desc + summary) | Background — chained |
| Create book **without** full_text | Skip | Generate (title + desc) | Synchronous |
| Update book | Skip | Regenerate with current fields | Synchronous |
| Backfill | Generate missing summaries | Regenerate all embeddings | Admin-triggered endpoint |

**Decision 5: Search API — dedicated endpoint with relevance scores**
- `GET /api/v1/books/search?q=...` — separate from the list endpoint
- Returns results ranked by cosine similarity with a relevance score per result
- Accessible to any authenticated user (customers need to search)
- A dedicated endpoint makes the intent explicit and avoids conflating listing with searching

**Decision 6: Testing strategy**
- **Unit tests with mocked embeddings**: Seed books with known vectors in the test DB. Verify search returns results in correct relevance order, handles edge cases (empty query, no results), and respects the response schema.
- **Semantic quality tests**: Seed books matching the README's examples ("mystery set in Tokyo", "sci-fi about time travel", irrelevant "cookbook"). Verify the right books rank first for the matching queries.
- **Smoke test**: Real OpenAI embedding call + real search against the live API to verify end-to-end integration.

### Implementation Notes

**Global LLM mock was necessary.** Once embedding generation was wired into `create_book` (synchronous for books without full_text), ALL existing book tests started failing because they hit the real OpenAI API. The fix was a global `autouse` LLM mock fixture in `conftest.py` that returns a zero vector for embeddings and a canned summary. Individual test modules (summary tests, search tests) override this with their own mocks when they need specific behaviour. This pattern — global no-op mock with per-module overrides — is the standard approach for external service dependencies in test suites.

**Search tests use crafted vectors, not real embeddings.** Rather than mocking OpenAI to return specific embeddings (which would test OpenAI's model, not our code), we seed books with manually constructed vectors where we control which are similar. This isolates the test to our search logic: pgvector cosine similarity, ranking, filtering, and response formatting. Real embedding quality is verified in the smoke test.

