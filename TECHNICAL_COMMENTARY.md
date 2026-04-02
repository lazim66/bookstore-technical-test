# Technical Commentary

## 1. Approach

The existing codebase has clean conventions and 59 passing tests. My priorities were to follow the established patterns, ensure zero test regressions, and build each feature incrementally. I also noticed the project had no git history and no way to verify the live API beyond Swagger UI, so early on I set up git for change tracking and planned an end-to-end smoke test script for real-world verification.

### Permissions

With exactly two roles (customer, admin), I planned a simple `role` field on the user model rather than a separate roles/permissions table. A many-to-many schema would add migration complexity and join overhead for zero benefit when the domain is binary.

- **Enforcement:** A `require_admin` FastAPI dependency that chains off `authenticate_user`. This is idiomatic FastAPI, integrates with the DI system, generates OpenAPI security docs automatically, and keeps authorization at the router layer rather than in service methods
- **Role assignment:** Beyond the minimum. A seeded admin on startup, an admin endpoint to create users with a role, and a promotion/demotion endpoint. The full lifecycle (bootstrap, create, promote, demote, delete) is more production-realistic and costs minimal extra code
- **Test strategy:** Make the existing `test_user` an admin so all 59 tests pass unchanged, then add a `customer_client` fixture for permission-denial tests. Refactoring ~32 existing tests for separate admin/customer clients would add churn for no functional benefit

### Book Summaries

LLM calls take 5-15 seconds, so I planned to use **FastAPI BackgroundTasks** for async generation. The API returns 201 immediately and the summary appears shortly after. Persistent task queues (like Celery or ARQ) would add infrastructure complexity disproportionate to this scope, though they'd be the right choice in production. The backfill endpoint serves as a recovery mechanism for any tasks lost to server restarts.

- **Concurrency control:** An `asyncio.Semaphore` with a configurable limit (`LLM_MAX_CONCURRENT_REQUESTS`, default 5). When backfilling many books, all tasks fire concurrently but the semaphore gates them so only N run at a time
- **LLM model:** GPT-5.4 Nano, OpenAI's latest generation optimised for summarization and data extraction. $0.20/M input tokens, 400K context window. All LLM configuration is environment-variable driven
- **Summaries are auto-generated but admin-editable.** Allowing overrides is zero-cost and useful when an admin wants to tweak tone or accuracy

### Semantic Search

The critical decision was **what to embed**:

- *Title + description only:* Too thin. A book titled "The Neon Veil" with description "A debut novel" would barely match "mystery novels set in Tokyo"
- *Full book text with chunking:* Novels are 60,000-100,000+ words but embedding models max out at ~6,000 words. This would require a full RAG pipeline (chunking, multiple vectors per book, result aggregation), which is disproportionate for catalog search
- *Title + description + summary:* The LLM-generated summary captures themes, genre, setting, and tone in 2-3 paragraphs. This is exactly what customers search by

I chose **title + description + summary**. The summary is a semantic compression of the entire book, purpose-built for discovery. Research confirms that embedding large, multi-topic text into a single vector dilutes meaning, so a focused summary produces a better embedding.

Since the embedding includes the summary, I planned to **chain them in the same background task**: generate summary first, then generate the embedding from the enriched text. For books without full_text, the embedding generates synchronously from title + description. On updates, it regenerates if searchable fields change. One clear code path per scenario.

- **Embedding model:** `text-embedding-3-small` (1536 dimensions). For the short texts we embed (~200-500 tokens), the quality difference versus the large model is negligible, while the cost is 6.5x lower
- **Vector storage:** pgvector with an HNSW index and cosine distance. HNSW can be created on an empty table (no training step) and has better query performance than IVFFlat for datasets under millions of rows

### Developer Experience

I noticed the project had no git tracking and no way to test the live system end-to-end. The pytest suite mocks authentication entirely (bypassing Redis sessions), so it can't verify things like:

- The real auth flow (signup, password hashing, login, Redis session, bearer token)
- Whether the seeded admin can actually log in
- Whether the LLM generates useful summaries with real API calls
- Whether semantic search actually finds the right books

I planned an httpx-based smoke test script (`just smoke-test`) that exercises the live Docker stack with real HTTP requests and real OpenAI calls. httpx is already a project dependency, and Python handles multi-step flows (login, capture token, use in subsequent requests) much more cleanly than shell scripts.

---

## 2. Implementation

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Docker Compose                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │   FastAPI App     │  │   PostgreSQL     │  │    Redis     │  │
│  │   (Port 8080)     │  │   + pgvector     │  │  (Port 6379) │  │
│  ├──────────────────┤  ├──────────────────┤  ├──────────────┤  │
│  │ • REST API        │  │ • Users (roles)  │  │ • Sessions   │  │
│  │ • RBAC            │  │ • Authors        │  │ • Auth       │  │
│  │ • Background      │  │ • Books (+ text, │  │              │  │
│  │   Tasks (LLM)     │  │   summary,       │  │              │  │
│  │ • Semantic Search  │  │   embeddings)    │  │              │  │
│  │ • OpenAI Client   │  │ • Orders         │  │              │  │
│  └────────┬──────────┘  └────────┬─────────┘  └──────┬───────┘  │
│           └──────────────────────┴───────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │   OpenAI API      │
                    │ • GPT-5.4 Nano    │
                    │   (summaries)     │
                    │ • text-embedding  │
                    │   -3-small        │
                    │   (search)        │
                    └───────────────────┘
```

### Database Schema (new fields marked with ★)

```
┌──────────────┐           ┌──────────────┐
│    users     │           │   authors    │
├──────────────┤           ├──────────────┤
│ id           │◄──┐       │ id           │◄─┐
│ email        │   │       │ name         │  │
│ full_name    │   │       │ bio          │  │
│ hashed_pwd   │   │       └──────────────┘  │
│ role ★       │   │                         │
│ is_active    │   │       ┌──────────────┐  │
└──────────────┘   │       │    books     │  │
                   │       ├──────────────┤  │
┌──────────────┐   │    ┌─►│ id           │  │
│    orders    │   │    │  │ title        │  │
├──────────────┤   │    │  │ author_id    │──┘
│ id           │   │    │  │ description  │
│ user_id      │───┘    │  │ full_text ★  │
│ book_id      │────────┘  │ summary ★    │
│ quantity     │           │ embedding ★  │
│ total_amount │           │ price        │
│ status       │           └──────────────┘
└──────────────┘
```

### New Endpoints


| Endpoint                     | Method | Access   | Purpose                               |
| ---------------------------- | ------ | -------- | ------------------------------------- |
| `/users`                     | POST   | Admin    | Create user with role                 |
| `/users/{id}/role`           | PATCH  | Admin    | Promote/demote user                   |
| `/users/{id}`                | DELETE | Admin    | Hard-delete user                      |
| `/books/{id}/summarize`      | POST   | Admin    | Generate summary for one book         |
| `/books/backfill-summaries`  | POST   | Admin    | Batch-generate summaries              |
| `/books/backfill-embeddings` | POST   | Admin    | Batch-generate embeddings             |
| `/books/search?q=...`        | GET    | Any user | Semantic search with relevance scores |


### Summary + Embedding Generation Flow

```
Book created with full_text:
    ┌──────────┐     ┌─────────────┐     ┌──────────────┐     ┌──────────┐
    │ Admin    │────►│ POST /books │────►│ 201 Created  │────►│ Response │
    │ Request  │     │ (immediate) │     │ (no summary  │     │ returned │
    └──────────┘     └──────┬──────┘     │  yet)        │     └──────────┘
                            │            └──────────────┘
                            ▼
                   ┌─────────────────┐
                   │ Background Task │
                   ├─────────────────┤
                   │ 1. Generate     │──► OpenAI GPT-5.4 Nano
                   │    summary      │
                   │ 2. Generate     │──► OpenAI text-embedding-3-small
                   │    embedding    │
                   │ 3. Save both    │──► PostgreSQL
                   └─────────────────┘

Book created without full_text:
    ┌──────────┐     ┌─────────────┐     ┌──────────────┐
    │ Admin    │────►│ POST /books │────►│ 201 Created  │
    │ Request  │     │ + embed     │     │ (with        │
    └──────────┘     │   (sync)    │     │  embedding)  │
                     └─────────────┘     └──────────────┘
```

### Project Structure (new files marked with ★)

```
technical-test-python/
├── src/
│   ├── db/
│   │   ├── models.py              # + role, full_text, summary, embedding
│   │   └── operations.py
│   ├── routes/v1/
│   │   ├── users/                 # + admin create, role management, delete
│   │   ├── authors/               # + require_admin on writes
│   │   ├── books/                 # + summary_service.py, search, backfill
│   │   └── orders/
│   ├── utils/
│   │   ├── auth.py                # + require_admin dependency
│   │   ├── llm.py                 # ★ OpenAI client (summaries + embeddings)
│   │   ├── seed.py                # ★ Database seeding (admin bootstrap)
│   │   └── redis.py
│   └── main.py
├── tests/
│   ├── unit/
│   │   ├── test_permission_endpoints.py  # ★ 36 permission tests
│   │   ├── test_summary_endpoints.py     # ★ 14 summary tests
│   │   ├── test_search_endpoints.py      # ★ 10 search tests
│   │   └── ... (existing tests unchanged)
│   └── conftest.py                # + admin/customer fixtures, LLM mock
├── scripts/
│   ├── smoke_test.py              # ★ End-to-end test (42 checks)
│   └── seed.py                    # ★ Standalone seeding
└── justfile                       # + smoke-test, seed recipes
```

### Deviations from Planned Approach

**Background task sessions needed their own DB connections.** The `SummaryService` initially shared the request's database session, but background tasks run after the request session closes. In tests, this meant the service couldn't see data created by the test. I refactored the service to accept a session factory, which tests can override with one bound to the test engine. The end result is cleaner separation between request-scoped and background operations.

**A review of the response schemas revealed `full_text` was being sent in list responses.** The initial `BookOutput` included `full_text`, which would send potentially large book texts for every item in list calls. I split it into `BookOutput` (for lists, without full_text) and `BookDetailOutput` (for single-book retrieval, with full_text).

**The end-to-end smoke test revealed a resilience issue.** When the OpenAI API was temporarily unavailable, the embedding generation in `create_book` threw an unhandled error, returning a 500 and preventing the book from being created at all. Embedding is a non-critical enhancement, so I wrapped it in error handling: book creation always succeeds, and the embedding can be backfilled later. This is the kind of issue that mocked unit tests can never catch since they never hit the real API.

### End-to-End Smoke Test **(Reviewers: please run `just smoke-test`)**

The best way to see every feature in action is to run the smoke test. It exercises the full system against the live Docker stack with real HTTP requests and real OpenAI calls, and takes about a minute:

```bash
just start             # Start all services
just smoke-test        # 42 checks with real LLM calls
```

The smoke test:
- Runs **42 checks** across 11 user stories covering all three deliverables
- Uses **real auth flows** (signup, login, Redis sessions, bearer tokens)
- Makes **real OpenAI calls** for summary generation and semantic search
- Shows the **actual generated summaries** and search results in the output
- Explains **what each test verifies and why**, so the output reads as a guided walkthrough
- **Cleans up after itself**, returning the DB to seed state (safe to run repeatedly)

Other useful commands:

```bash
just test              # Run 119 unit tests
just seed              # Re-seed admin without restarting
just db-reset          # Reset database (drops all data)
```

### Verification Results

I ran the smoke test with real OpenAI calls and inspected the outputs:

**Summary quality:**

- Background task generated a ~160-word summary in ~4 seconds
- The summary accurately captured book themes: *"Inspector Kenji Tanaka investigates the disappearance of three prominent businessmen from Tokyo's Golden Gai..."*

**Semantic search quality:**

- "mystery novels set in Tokyo" found "The Neon Veil" first (relevance=0.56), even though the title contains neither "mystery" nor "Tokyo"
- "science fiction about time travel" found "Chrono Drift" first
- "detective investigating disappearances in Japan" still found "The Neon Veil" via semantic meaning

These results validated the decision to embed the summary. It provides rich semantic signal that matches customer intent even when the search words don't appear in the title or description.

### Test Summary


| Layer                     | Count | What it tests                                                                      |
| ------------------------- | ----- | ---------------------------------------------------------------------------------- |
| Unit/integration (pytest) | 119   | Business logic, permissions, API contracts, concurrency (mocked external services) |
| End-to-end (smoke test)   | 42    | Full stack with real auth, real LLM, real semantic search (live Docker containers) |


---

## 3. Discussion

### What went well

**Feature-by-feature development with running documentation.** Building each deliverable sequentially (permissions, then summaries, then search) meant each feature built naturally on the previous one. The running log of decisions captured reasoning as it happened rather than retroactively.

**The smoke test created a genuine feedback loop.** What started as a "verify the live API works" script became essential across all three features. It caught real integration bugs (OpenAI API parameter changes, resilience issues), validated LLM output quality (the actual summaries are visible in the output), and proved semantic search works via meaning rather than keywords. In hindsight, it was a very impactful addition to the project.

**Architectural separation paid off.** Keeping the LLM service, summary service, and book service as distinct layers made each feature independently testable. When semantic search needed embeddings, it plugged into the same LLM service the summary feature already used.

### What was challenging

**Testing background tasks that use independent database sessions.** FastAPI's dependency override system works well for request-scoped mocks, but background tasks create their own sessions that can't see uncommitted test data. Getting the fixture design right (injectable session factory, test-engine-bound sessions) took several iterations, but the final pattern cleanly separates request-scoped operations from background work.

**Verifying concurrent execution limits.** Testing that the semaphore actually restricts parallelism required a mock with an atomic counter tracking peak concurrency, plus controlled delays to ensure tasks overlap. The test is thorough but was tricky to wire up correctly.

### What I'd do differently with more time

**Scaling for production:**

- **Alembic migrations** instead of `create_all` for proper schema evolution. The current approach works for development but doesn't handle adding/removing columns in a running production database
- **Persistent task queue** (Celery, ARQ, or similar) for summary and embedding generation. BackgroundTasks are tied to the web server process; if it restarts, pending tasks are lost. A persistent queue adds retry logic, dead-letter handling, and the ability to scale workers independently
- **Separate connection pools** for request handling and background tasks so bulk backfill operations don't starve incoming API requests
- **Rate limiting and caching.** Rate limiting (Redis-backed middleware) across all API endpoints, and response caching on the search endpoint. Each search query currently makes an OpenAI embedding call, which at high traffic would be both slow and expensive without caching common queries
- **Pagination** on list endpoints and search results. The current implementation returns all results, which won't scale with a large catalog

**Feature improvements:**

- **Hybrid search** combining vector similarity with keyword matching (e.g., PostgreSQL full-text search). Pure vector search can miss exact title matches that a keyword search would catch instantly
- **Full-text chunking with reranking** for books where the summary alone doesn't capture enough detail. Chunk the full text, retrieve candidate chunks via vector similarity, then rerank with a cross-encoder model for higher precision
- **Search filters** combining semantic search with structured criteria like price range, author, and publication date
- **Book recommendations** building on the existing embedding infrastructure. Add wishlists and reviews/ratings so customers can express interest, then combine purchase history, ratings, and embedding similarity to power a recommendations system. The vectors and cosine distance queries already exist, so "find similar books" is a query away. Layering in behavioural signals (what customers bought, wishlisted, and rated highly) would make recommendations increasingly personalised
- **Batch book import** with concurrent summary and embedding generation. Currently books are added one at a time; a CSV/JSON bulk import endpoint would let admins onboard entire catalogs efficiently using the existing concurrency controls

**Observability:**

- Structured logging, request tracing, and metrics on LLM call latency, success rates, and token usage. Essential for understanding costs at scale and debugging production issues

