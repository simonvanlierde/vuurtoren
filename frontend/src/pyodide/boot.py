"""Runs once inside the Pyodide worker, then serves dispatch(). The mechanism (the real
FastAPI app in wasm plus these two shims) is proven by the e2e-pyodide Playwright smoke."""

import json
import os
from pathlib import Path

os.environ["VUURTOREN_DB"] = "/tmp/vuurtoren.db"  # MEMFS; default_db_path() reads this

# Shim 1: single-threaded wasm can't start the threadpool FastAPI uses for sync handlers
# and yield-dependency teardown ("can't start new thread"). Both run_in_threadpool and
# contextmanager_in_threadpool bottom out in anyio.to_thread.run_sync; run that work
# inline on the event loop. Safe here: the DB is in-memory and requests are one-at-a-time.
import anyio.to_thread  # noqa: E402


async def _run_sync_inline(func, *args, **kwargs):  # noqa: ANN001, ANN202, ARG001
    return func(*args)


anyio.to_thread.run_sync = _run_sync_inline

# Shim 2: build the schema directly (the tests' approach — a fresh in-wasm DB has no
# migrations to replay). `upgrade_to_head` returns early under emscripten on its own, so
# the app's own _engine() never reaches alembic, which isn't shipped to the browser.
import vuurtoren.db as vdb  # noqa: E402
import vuurtoren.tables  # noqa: E402, F401  (registers models on Base.metadata)
from sqlalchemy.orm import sessionmaker  # noqa: E402
from vuurtoren.seed import load_household_spec, seed_household  # noqa: E402

_engine = vdb.make_engine(vdb.default_db_path())
vdb.Base.metadata.create_all(_engine)

with sessionmaker(bind=_engine)() as _s:
    seed_household(_s, load_household_spec(Path("/assets/household.example.toml")))
    _s.commit()

from vuurtoren.api import app  # noqa: E402


async def dispatch(method, path, query, body):  # noqa: ANN001, ANN201
    """Drive the ASGI app for one request; return a JSON string {status, headers, body}."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        # A Host header, because the app refuses requests whose Host is not a local name
        # (DNS-rebinding guard); a worker request has none of its own.
        "headers": [(b"host", b"localhost"), (b"content-type", b"application/json")],
        "scheme": "http",
        "server": ("wasm", 80),
        "client": ("wasm", 0),
    }
    state = {"done": False}

    async def receive():
        if state["done"]:
            return {"type": "http.disconnect"}
        state["done"] = True
        return {"type": "http.request", "body": body.encode(), "more_body": False}

    out = {"status": 500, "headers": [], "body": b""}

    async def send(msg):
        if msg["type"] == "http.response.start":
            out["status"] = msg["status"]
            out["headers"] = [[k.decode(), v.decode()] for k, v in msg["headers"]]
        elif msg["type"] == "http.response.body":
            out["body"] += msg.get("body", b"")

    await app(scope, receive, send)
    return json.dumps(
        {"status": out["status"], "headers": out["headers"], "body": out["body"].decode()}
    )
