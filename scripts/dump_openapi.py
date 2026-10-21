"""Write the API's OpenAPI schema to a JSON file, without starting a server.

`pnpm -C frontend run gen:api` runs this, then generates `frontend/src/lib/api.gen.ts`
from the file. `tests/test_openapi.py` fails when the committed file is stale.

Usage: uv run python scripts/dump_openapi.py frontend/src/lib/openapi.json
"""

import json
import sys
from pathlib import Path

from vuurtoren.api import app


def schema_text() -> str:
    """The schema exactly as it is committed: two-space indent, trailing newline."""
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    Path(sys.argv[1]).write_text(schema_text(), encoding="utf-8")
