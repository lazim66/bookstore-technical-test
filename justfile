# Justfile for technical-test-api development

# Default recipe (list all commands)
default:
    @just --list

# Build Docker images
build:
    docker compose build

# Start all services
start:
    docker compose up -d
    docker compose logs -f api

# Stop all services
stop:
    docker compose down

# Open shell in API container
shell:
    docker compose exec api /bin/bash

# Run tests
test:
    docker compose exec api pytest tests/ -v

# Reset database (drop and recreate)
db-reset:
    docker compose down db
    docker volume rm technical-test-python_postgres_data || true
    docker compose up -d db
    @echo "Waiting for database to be ready..."
    @sleep 5
    docker compose up -d api
    @echo "Database reset complete!"