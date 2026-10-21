"""Serve the example household for the Playwright suites.

Run from the repo root (the Playwright webServer does):

    uv run python scripts/smoke_server.py

Env knobs (all optional):
    VUURTOREN_SMOKE_PORT   port, default 8123
    VUURTOREN_SMOKE_EMPTY  "1" skips seeding — the first-run onboarding path
    VUURTOREN_SMOKE_WAIT   "1" waits for src/vuurtoren/static/index.html before starting,
                           so a second server entry need not race the first's build

Uses a throwaway SQLite file and `household.example.toml`, so it never touches
`data/vuurtoren.db` or real data.
"""

import os
import tempfile
import time
from pathlib import Path

os.environ["VUURTOREN_DB"] = str(Path(tempfile.mkdtemp(prefix="vuurtoren-smoke-")) / "smoke.db")
os.environ["VUURTOREN_HOUSEHOLD"] = "household.example.toml"

if os.environ.get("VUURTOREN_SMOKE_WAIT") == "1":
    deadline = time.monotonic() + 180
    while not Path("src/vuurtoren/static/index.html").exists():
        if time.monotonic() > deadline:
            msg = (
                "src/vuurtoren/static/index.html never appeared - "
                "is the sibling webServer's build running?"
            )
            raise TimeoutError(msg)
        time.sleep(1)

import uvicorn
from sqlalchemy.orm import sessionmaker

from vuurtoren.api import _engine, app
from vuurtoren.seed import seed_household

if __name__ == "__main__":
    if os.environ.get("VUURTOREN_SMOKE_EMPTY") != "1":
        with sessionmaker(bind=_engine())() as session:
            seed_household(session)
            session.commit()
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("VUURTOREN_SMOKE_PORT", "8123")))
