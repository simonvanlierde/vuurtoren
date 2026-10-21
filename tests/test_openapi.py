"""The committed OpenAPI schema matches the app, so the generated frontend types do too.

`frontend/src/lib/api.gen.ts` is generated from `frontend/src/lib/openapi.json`; a vitest
test checks that step. This one checks the step before it. On failure, run
`pnpm -C frontend run gen:api` and commit both files.
"""

import runpy
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def test_the_committed_openapi_schema_is_current() -> None:
    """A changed request or response model without a re-run of gen:api fails here."""
    schema_text = runpy.run_path(str(_ROOT / "scripts" / "dump_openapi.py"))["schema_text"]
    committed = (_ROOT / "frontend" / "src" / "lib" / "openapi.json").read_text(encoding="utf-8")
    assert committed == schema_text(), "stale: run `pnpm -C frontend run gen:api`"
