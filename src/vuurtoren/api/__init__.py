"""FastAPI app.

One service, loopback only, no auth. CRUD over the household tables, `/api/project`
(assembles a `PlanInput` from the database and calls `engine.project()` — the engine
itself never touches the database), `/api/export` (the whole household as one JSON
document), and a static mount for the built frontend.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import Headers
from starlette.middleware.trustedhost import TrustedHostMiddleware

from vuurtoren.api import compute, crud, export, meta, pricing, reporting
from vuurtoren.api.deps import _engine, get_session

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette.types import ASGIApp, Receive, Scope, Send

__all__ = ["app", "get_session", "main"]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Open and migrate the database before the first request is served.

    Migrating on demand instead would put `alembic upgrade` on the request path, where
    several requests arriving together each run one in a worker thread — alembic keeps
    its environment in process-global state and does not survive that.
    """
    _engine()
    yield


app = FastAPI(title="vuurtoren", lifespan=lifespan)

_LOCAL_HOSTS = ["127.0.0.1", "localhost", "testserver"]
"""Host names the server answers to, on any port. Loopback only; "localhost" is also what
the Pyodide worker sends, and "testserver" is the test client's."""
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class _SameOriginWrites:
    """Refuse a state-changing request that a browser sent from another site (403).

    The server has no auth, so any page the user visits could otherwise POST to it. A
    browser sets `Origin` on such a request; a request without one (curl, the Pyodide
    worker) is let through. Same-origin is the Origin's host:port equal to the Host
    header, which also holds behind the Vite dev proxy, since it forwards both unchanged.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in _SAFE_METHODS:
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            if origin is not None and urlsplit(origin).netloc != headers.get("host"):
                refused = JSONResponse({"detail": "cross-origin request refused"}, status_code=403)
                await refused(scope, receive, send)
                return
        await self.app(scope, receive, send)


# Added last runs first: the Host check (DNS rebinding) wraps the Origin check.
app.add_middleware(_SameOriginWrites)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_LOCAL_HOSTS)


@app.exception_handler(IntegrityError)
def _integrity_error_handler(_request: Request, exc: IntegrityError) -> JSONResponse:
    """Answer a FK or UNIQUE violation with 409 rather than a 500.

    Deleting a row another row still references, or posting a duplicate PricePoint for
    the same account+date, is a client error, not a server one.
    """
    return JSONResponse(status_code=409, content={"detail": str(exc.orig)})


for _module in (crud, reporting, compute, export, meta, pricing):
    app.include_router(_module.router)

# Static mount for the built frontend — added last so it never shadows /api.
_static_dir = Path(__file__).parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")


def main() -> None:
    """Serve the app on loopback — the `vuurtoren` console script."""
    import uvicorn  # noqa: PLC0415 -- deferred so importing the app does not start the server

    uvicorn.run(app, host="127.0.0.1", port=8000)
