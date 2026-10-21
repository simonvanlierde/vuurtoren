# Run `just` to list the available developer commands.

default:
    @just --list

# Install Python and frontend dependencies.
install:
    uv sync
    pnpm -C frontend install

# Start the API server at http://127.0.0.1:8000.
api:
    uv run vuurtoren

# Start the Vite development server with API proxying and hot reload.
ui:
    pnpm -C frontend dev

# Start the API and hot-reloading UI together; Ctrl-C stops both.
dev:
    @uv run vuurtoren & backend_pid=$!; trap 'kill "$backend_pid" 2>/dev/null' EXIT INT TERM; pnpm -C frontend dev

# Build the frontend into the API's static mount.
build:
    pnpm -C frontend build

# Build the standalone, browser-only version.
build-browser:
    pnpm -C frontend build:browser

# Run the Python test suite.
test:
    uv run pytest

# Run the frontend test suite.
test-ui:
    pnpm -C frontend test

# Run Python formatting, linting, and type checks.
check-python:
    uv run ruff format --check .
    uv run ruff check .
    uv run ty check

# Run frontend checks.
check-ui:
    pnpm -C frontend check

# Run every pre-commit gate.
check: check-python check-ui test test-ui build

# Bring the local database schema to the latest revision.
migrate:
    uv run alembic upgrade head

# Create an Alembic migration from the current schema changes.
migration message:
    uv run alembic revision --autogenerate -m "{{message}}"
