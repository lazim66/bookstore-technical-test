# System Overview

This document provides a comprehensive overview of the pre-built backend system. Read this first to understand the architecture, technologies, and patterns used in this application.

## System Architecture

This application consists of three containerized services working together:

```
┌─────────────────────────────────────────────────────────────────┐
│                         Docker Compose                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │   FastAPI App    │  │   PostgreSQL     │  │    Redis     │   │
│  │   (Port 8080)    │  │   (Port 5432)    │  │  (Port 6379) │   │
│  ├──────────────────┤  ├──────────────────┤  ├──────────────┤   │
│  │ • REST API       │  │ • Users          │  │ • Sessions   │   │
│  │ • Business Logic │  │ • Authors        │  │ • Auth       │   │
│  │ • Validation     │  │ • Books          │  │ • Caching    │   │
│  │ • Auth           │  │ • Orders         │  │              │   │
│  └────────┬─────────┘  └────────┬─────────┘  └──────┬───────┘   │
│           │                     │                   │           │
│           └─────────────────────┴───────────────────┘           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Database Schema

The application uses PostgreSQL with four main tables:

```
┌─────────────────────────────────────────────────────────────────┐
│                       Database Tables                           │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐           ┌──────────────┐
│    users     │           │   authors    │
├──────────────┤           ├──────────────┤
│ id           │◄──┐       │ id           │◄─┐
│ email        │   │       │ name         │  │
│ full_name    │   │       │ bio          │  │
│ hashed_pwd   │   │       │ created_at   │  │
│ is_active    │   │       │ updated_at   │  │
│ created_at   │   │       └──────────────┘  │
│ updated_at   │   │                         │
└──────────────┘   │       ┌──────────────┐  │
                   │       │    books     │  │
                   │       ├──────────────┤  │
┌──────────────┐   │    ┌─►│ id           │  │
│    orders    │   │    │  │ title        │  │
├──────────────┤   │    │  │ author_id    │──┘
│ id           │   │    │  │ description  │
│ user_id      │───┘    │  │ price        │
│ book_id      │────────┘  │ published_at │
│ quantity     │           │ created_at   │
│ total_amount │           │ updated_at   │
│ status       │           └──────────────┘
│ created_at   │
│ updated_at   │
└──────────────┘
```

## API Endpoints

The API provides full CRUD operations for Users, Authors, Books, and Orders.

**Explore all endpoints interactively at: http://localhost:8080/docs**

The auto-generated Swagger UI documentation allows you to:
- See all available endpoints and their parameters
- Test endpoints directly from your browser
- View request/response schemas
- Understand authentication requirements

## Request Flow

The FastAPI backend follows a 4-layer architecture. Here's how a typical request flows through the system:

```
HTTP Request (POST /api/v1/books)
    ↓
Router (validates request, extracts data)
    ↓
Service (applies business rules)
    ↓
Repository (saves to database)
    ↓
Database (PostgreSQL)
    ↓
Response flows back up through layers
```

## Authentication System

The API uses **session-based authentication**:

1. **Sign up**: Create account with email/password
   ```bash
   POST /api/v1/users/signup
   { "email": "test@example.com", "password": "password123", "full_name": "Test User" }
   ```

2. **Login**: Exchange credentials for access token
   ```bash
   POST /api/v1/users/login
   { "email": "test@example.com", "password": "password123" }
   →
   { "access_token": "abc123...", "token_type": "bearer", "user": {...} }
   ```

3. **Authenticated requests**: Include token in header
   ```bash
   Authorization: Bearer abc123...
   ```

Tokens are stored in Redis and expire after 30 minutes (configurable in `.env`).

**Note**: This is a simplified authentication system for demonstration. It mimics the pattern of OAuth2 (credentials → bearer token → authenticated requests) but lacks production security features like token refresh, CSRF protection, and proper OAuth2/OIDC implementation.

## Project Structure

```
technical-test-python/
├── src/
│   ├── db/
│   │   ├── models.py              # Database models (DBUser, DBAuthor, DBBook, DBOrder)
│   │   └── operations.py          # Database connection setup
│   ├── routes/
│   │   └── v1/
│   │       ├── __init__.py        # Router registration
│   │       ├── users/             # User resource (reference implementation)
│   │       ├── authors/           # Author resource
│   │       ├── books/             # Book resource
│   │       └── orders/            # Order resource
│   ├── utils/
│   │   ├── auth.py                # Authentication helpers
│   │   └── redis.py               # Redis client
│   ├── main.py                    # FastAPI app initialization
│   └── settings.py                # Configuration from environment
├── tests/
│   ├── unit/
│   │   ├── test_user_endpoints.py
│   │   ├── test_author_endpoints.py
│   │   ├── test_book_endpoints.py
│   │   └── test_order_endpoints.py
│   └── conftest.py                # Pytest fixtures (client, services, etc.)
├── docker-compose.yaml            # 3 services: api, db, redis
├── Dockerfile                     # Python 3.11 container
├── pyproject.toml                 # Dependencies and config
└── justfile                       # Command shortcuts
```

## Getting Started

### Starting the Application

```bash
# Start all services
just start
# Or without just:
docker compose up -d
docker compose logs -f api
```

The API will be available at:
- **API**: http://localhost:8080
- **Interactive docs**: http://localhost:8080/docs
- **Health check**: http://localhost:8080/health

### Running Tests

```bash
# All tests
just test

# Specific test file
docker compose exec api pytest tests/unit/test_author_endpoints.py -v

# With coverage report
docker compose exec api pytest tests/ --cov=src --cov-report=term-missing

# Stop on first failure
docker compose exec api pytest tests/ -x
```

### Debugging

**Access container shell:**
```bash
just shell
# Or: docker compose exec api /bin/bash
```

**View logs:**
```bash
docker compose logs -f api
```

**Reset database:**
```bash
just db-reset
# Or: docker compose down db && docker volume rm technical-test-python_postgres_data
```

### Hot Reloading

Code changes are automatically detected. The API server will reload when you modify files in `src/`.

---

## Appendix

### A. Containerization with Docker Compose

The entire application stack is containerized and orchestrated using Docker Compose, making it easy to run locally without managing dependencies manually.

#### Container Architecture

**API Container (`technical-test-api`)**
- Built from `Dockerfile` using Python 3.11 slim image
- Runs FastAPI application with Uvicorn ASGI server
- Hot-reload enabled for development (code changes trigger automatic restart)
- Exposes port 8080 for HTTP traffic
- Volume-mounted source code for live development
- Connects to PostgreSQL and Redis containers via Docker network

**Database Container (`technical-test-db`)**
- PostgreSQL 13 official image
- Persistent data storage via Docker volume (`postgres_data`)
- Exposes port 5432 for direct database access if needed
- Automatically creates `technical_test` database on first start
- Tables are created automatically by SQLModel on application startup

**Redis Container (`technical-test-redis`)**
- Redis 7 Alpine image (lightweight)
- Stores user sessions and authentication tokens
- Persistent storage via Docker volume (`redis_data`)
- Exposes port 6379
- Configured with append-only file (AOF) persistence

#### Network Communication

All containers communicate via a Docker bridge network:
- **API → Database**: PostgreSQL connection via `postgresql+asyncpg://postgres:postgres@db:5432/technical_test`
- **API → Redis**: Session storage via `redis://redis:6379`
- **Host → API**: HTTP requests via `http://localhost:8080`

### B. Python Backend Architecture

The FastAPI backend follows a **4-layer architecture** with clear separation of concerns:

#### Layer 1: Router (`router.py`)
- Handles HTTP requests and responses
- Defines API endpoints with FastAPI decorators
- Manages status codes and request/response models
- Uses dependency injection to get services

#### Layer 2: Service (`service.py`)
- Contains business logic and validation
- Orchestrates between multiple repositories
- Handles exceptions and error responses
- Interface between HTTP layer and data layer

#### Layer 3: Repository (`repository.py`)
- Direct database operations (CRUD)
- Constructs and executes database queries
- Returns database models
- No business logic or HTTP concerns

#### Layer 4: Schema (`schema.py`)
- Request validation (CreateInput, UpdateInput)
- Response serialization (Output models)
- Pydantic models separate from database models

#### Request Flow Example

```
HTTP Request (POST /api/v1/books)
    ↓
Router (validates request, extracts data)
    ↓
Service (applies business rules)
    ↓
Repository (saves to database)
    ↓
Database (PostgreSQL)
    ↓
Response flows back up through layers
```

### C. Tech Stack

**Backend Framework**
- **FastAPI** - Modern, async-first Python web framework with automatic OpenAPI documentation
- **Uvicorn** - Lightning-fast ASGI server
- **Pydantic** - Data validation using Python type hints

**Database & ORM**
- **PostgreSQL** - Production-grade relational database
- **SQLModel** - Modern ORM combining SQLAlchemy and Pydantic for type-safe database operations
- **Asyncpg** - High-performance async PostgreSQL driver

**Authentication & Sessions**
- **Redis** - In-memory data store for session management
- **Bcrypt** - Secure password hashing
- **Session-based auth** - Bearer token pattern with Redis-backed sessions

**Testing**
- **Pytest** - Modern Python testing framework
- **Pytest-asyncio** - Async test support
- **HTTPX** - Async HTTP client for API testing

**Development Tools**
- **Docker & Docker Compose** - Container orchestration
- **Just** - Command runner for common tasks (optional)
- **UV** - Fast Python package installer (used in Dockerfile)
