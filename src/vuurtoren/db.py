"""Database plumbing: the Money type, the engine factory, schema creation."""

import os
import sys
import threading
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import TYPE_CHECKING, override

from sqlalchemy import Connection, Engine, Float, Integer, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

if TYPE_CHECKING:
    import sqlite3


class Base(DeclarativeBase):
    """Declarative base for every table in tables.py."""

    # SQLAlchemy 2.1 maps a bare `float` to Double, 2.0 to Float. Both are REAL in
    # SQLite, so pinning Float keeps the migrated schema and the models in step on
    # either version without a table rebuild.
    type_annotation_map = {float: Float}  # noqa: RUF012  # read by SQLAlchemy, never mutated


_CENTS = Decimal("0.01")

# NOTE: SQLite has no exact decimal type, hence Money and ExactDecimal. Postgres would
# give exact decimals natively, at the cost of the single-file, self-hosted setup.


class Money(TypeDecorator[Decimal]):
    """Decimal in Python, integer eurocents in SQLite.

    SQLite has no decimal type and SQLAlchemy's Numeric silently round-trips through
    float there, so money is stored as an exact integer of minor units instead.
    """

    impl = Integer
    cache_ok = True

    @override
    def process_bind_param(self, value: Decimal | None, dialect: object) -> int | None:
        """Round a Decimal to whole eurocents for storage."""
        if value is None:
            return None
        return int((Decimal(value) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))

    @override
    def process_result_value(self, value: int | None, dialect: object) -> Decimal | None:
        """Turn stored eurocents back into a 2dp Decimal."""
        if value is None:
            return None
        return (Decimal(value) / 100).quantize(_CENTS)


class ExactDecimal(TypeDecorator[Decimal]):
    """Decimal in Python, exact-precision text in SQLite.

    For values that are not money — exchange rates, unit counts — where SQLAlchemy's
    Numeric would round-trip through a C double (lossy) and Money would quantize to
    cents (also lossy, just differently). This type stores the arbitrary-precision
    decimal verbatim as text, so it never loses digits either way.
    """

    impl = String
    cache_ok = True

    @override
    def process_bind_param(self, value: Decimal | None, dialect: object) -> str | None:
        """Serialise a Decimal to its exact text form."""
        if value is None:
            return None
        return str(value)

    @override
    def process_result_value(self, value: str | None, dialect: object) -> Decimal | None:
        """Parse the stored text back into a Decimal, digit for digit."""
        if value is None:
            return None
        return Decimal(value)


# NOTE: resolved against the source checkout, so an installed wheel would not find it.
# That is already true of the default database path below, and this app is run from its
# own directory; packaging the migrations is the fix if that ever stops holding.
_MIGRATIONS = Path(__file__).parents[2] / "migrations"


def default_db_path() -> Path:
    """The SQLite file the app opens, and the one the alembic CLI migrates.

    Both sides resolve it here so `alembic upgrade head` in a shell and the upgrade the
    app runs at startup can never end up pointed at different files.
    """
    env = os.environ.get("VUURTOREN_DB")
    return Path(env) if env else Path("data/vuurtoren.db")


def make_engine(path: Path | str) -> Engine:
    """Build the SQLite engine for `path`, with WAL, foreign keys and a busy timeout."""
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection: sqlite3.Connection, _record: object) -> None:
        # Python's sqlite3 driver picks where transactions begin, and it picks wrong: it
        # opens one before INSERT/UPDATE/DELETE but never before DDL, so DDL commits as
        # it runs and a migration that fails halfway leaves the half it managed. SQLite
        # has transactional DDL; only the driver throws it away. Handing BEGIN to
        # SQLAlchemy below gets it back.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL admits one writer at a time and SQLite's default busy timeout is 0, so a
        # second writer fails instantly rather than waiting for the first to finish.
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _begin(connection: Connection) -> None:
        connection.exec_driver_sql("BEGIN")

    return engine


def create_all(engine: Engine) -> None:
    """Create any table in tables.py that does not exist yet.

    This is the tests' fast path to a schema, and it only ever *adds* tables — it will
    not notice a column that appeared on a mapping after the file was written. Anything
    holding a database across a schema change wants `upgrade_to_head` instead;
    `test_migrations.py` pins the two to the same result.
    """
    from vuurtoren import tables  # noqa: F401, PLC0415 -- registers the mappings; top-level cycles

    Base.metadata.create_all(engine)


# Alembic's EnvironmentContext installs and removes its proxies in process-global module
# dicts, so two upgrades running at once corrupt each other's state — the symptom is a
# KeyError on teardown, not a database error. The app hits this on a cold start, where
# several requests land in the threadpool before the cached engine exists.
_UPGRADE_LOCK = threading.Lock()


def upgrade_to_head(engine: Engine) -> None:
    """Run every migration `engine`'s database has not seen yet.

    On an empty file that means creating the schema from scratch, so this is the only
    call the app needs at startup.

    A no-op in the browser: alembic is not shipped to wasm (no wheel, and there are no
    migrations to replay against a database created fresh in MEMFS every load). The
    condition lives here rather than as a patch in the boot script, where nothing
    type-checks it.
    """
    if sys.platform == "emscripten":
        return

    from alembic import command  # noqa: PLC0415 -- alembic loads env.py, which imports this module
    from alembic.config import Config  # noqa: PLC0415

    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS))
    with _UPGRADE_LOCK, engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
