"""Tests that the migrations describe the same schema the mappings do.

The tests build their databases with `create_all`, which is fast but only ever adds
whole tables; the app builds its own with `upgrade_to_head`. Nothing keeps those two in
step on its own — a column added to `tables.py` without a matching revision passes every
other test in this suite and then fails at runtime with "no such column". That is the
drift these tests exist to catch.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

from vuurtoren.db import Base, create_all, make_engine, upgrade_to_head
from vuurtoren.tables import AccountRow  # noqa: F401  # registers the mappings

if TYPE_CHECKING:
    from pathlib import Path


def _columns(engine: Engine) -> dict[str, set[str]]:
    inspector = inspect(engine)
    return {
        name: {column["name"] for column in inspector.get_columns(name)}
        for name in inspector.get_table_names()
        if name != "alembic_version"  # alembic's own bookkeeping, not part of the model
    }


def test_migrations_produce_the_mapped_schema(tmp_path: Path) -> None:
    """Running every migration leaves exactly the tables and columns the mappings declare."""
    migrated = make_engine(tmp_path / "migrated.db")
    upgrade_to_head(migrated)

    created = make_engine(tmp_path / "created.db")
    create_all(created)

    assert _columns(migrated) == _columns(created)


def test_no_mapping_change_is_missing_a_migration(tmp_path: Path) -> None:
    """Autogenerate against the migrated schema finds nothing left to do.

    This is the stricter half: it compares types and constraints too, so it fails on a
    column whose *definition* changed as well as on one that was added outright.
    """
    engine = make_engine(tmp_path / "head.db")
    upgrade_to_head(engine)

    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diff = compare_metadata(context, Base.metadata)

    assert diff == [], f"tables.py has changes with no migration: {diff}"


def test_concurrent_upgrades_do_not_collide(tmp_path: Path) -> None:
    """Several threads may upgrade at once — the app's cold start does exactly this.

    Alembic keeps its environment in process-global module state, so unserialised
    upgrades corrupt each other and fail with a KeyError while tearing the context down.
    """
    threads_n = 3
    barrier = threading.Barrier(threads_n)
    failures: list[BaseException] = []

    def upgrade(index: int) -> None:
        barrier.wait()
        try:
            upgrade_to_head(make_engine(tmp_path / f"concurrent{index}.db"))
        except BaseException as exc:  # noqa: BLE001 -- the assertion below is the report
            failures.append(exc)

    threads = [threading.Thread(target=upgrade, args=(i,)) for i in range(threads_n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
