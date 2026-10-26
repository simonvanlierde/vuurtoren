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

# Mutation testing over the Dutch tax code and solve.py (see [tool.mutmut]). Narrow it
# with mutant globs: `just mutation 'vuurtoren.solve*'`. Survivors never fail the run;
# it lists functions with more survivors than tests/mutation-baseline.txt.
[doc('Mutation testing over tax/nl and solve.py, reporting survivors beyond the baseline')]
mutation *mutants:
    #!/usr/bin/env bash
    set -euo pipefail
    # Mutant globs pass through to mutmut, not the shell.
    set -f
    # Low priority on half the cores by default, so the machine stays usable.
    nice -n 10 uv run --group mutation mutmut run --max-children "${MUTMUT_JOBS:-$(( ($(nproc) + 1) / 2 ))}" {{ mutants }}
    mkdir -p reports/mutation
    uv run --group mutation mutmut results | sed -n 's/^ *\(.*\): survived$/\1/p' | sort > reports/mutation/survivors.txt
    # Mutant numbers shift whenever a function changes, so compare survivor counts per function.
    sed 's/__mutmut_[0-9]*$//' reports/mutation/survivors.txt | sort | uniq -c \
        | awk 'FILENAME == ARGV[1] { base[$2] = $1; next } $1 > base[$2] { print $2, base[$2] + 0, "->", $1 }' \
            tests/mutation-baseline.txt - > reports/mutation/new-survivors.txt
    echo "$(wc -l < reports/mutation/survivors.txt) survivors; functions above baseline:"
    cat reports/mutation/new-survivors.txt

# Rebaseline after triaging survivors. Only from a full run: it replaces the whole file,
# so a narrowed run would drop every other function.
[doc('Rewrite tests/mutation-baseline.txt from the last full mutation run')]
mutation-baseline:
    sed 's/__mutmut_[0-9]*$//' reports/mutation/survivors.txt | sort | uniq -c | awk '{ print $1, $2 }' > tests/mutation-baseline.txt
