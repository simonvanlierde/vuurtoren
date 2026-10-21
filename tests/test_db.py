"""Tests for the Money and ExactDecimal SQLAlchemy column types (invariant 4 in CONTRIBUTING.md)."""

from __future__ import annotations

import contextlib
import sys
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, MetaData, Table, insert, inspect, select, text
from sqlalchemy.exc import OperationalError

from vuurtoren.db import ExactDecimal, Money, create_all, make_engine, upgrade_to_head

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_money_round_trips_through_sqlite_exactly(tmp_path: Path) -> None:
    """A Money column round-trips a Decimal amount byte-exactly as a Decimal."""
    engine = make_engine(tmp_path / "t.db")
    metadata = MetaData()
    t = Table("t", metadata, Column("id", Integer, primary_key=True), Column("amount", Money))
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(insert(t).values(id=1, amount=Decimal("12345.01")))
        got = conn.execute(select(t.c.amount)).scalar_one()

    assert got == Decimal("12345.01")
    assert isinstance(got, Decimal)


def test_money_stores_integer_cents(tmp_path: Path) -> None:
    """A Money column stores its value as integer cents on disk, not a float."""
    engine = make_engine(tmp_path / "t.db")
    metadata = MetaData()
    t = Table("t", metadata, Column("id", Integer, primary_key=True), Column("amount", Money))
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(insert(t).values(id=1, amount=Decimal("12.34")))
        raw = conn.exec_driver_sql("SELECT amount FROM t").scalar_one()

    assert raw == 1234


def test_money_rounds_half_up(tmp_path: Path) -> None:
    """A Money column rounds a half-cent value up rather than to even."""
    engine = make_engine(tmp_path / "t.db")
    metadata = MetaData()
    t = Table("t", metadata, Column("id", Integer, primary_key=True), Column("amount", Money))
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(insert(t).values(id=1, amount=Decimal("0.005")))
        got = conn.execute(select(t.c.amount)).scalar_one()

    assert got == Decimal("0.01")


def test_money_handles_none(tmp_path: Path) -> None:
    """A Money column round-trips NULL as None, not zero."""
    engine = make_engine(tmp_path / "t.db")
    metadata = MetaData()
    t = Table("t", metadata, Column("id", Integer, primary_key=True), Column("amount", Money))
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(insert(t).values(id=1, amount=None))
        assert conn.execute(select(t.c.amount)).scalar_one() is None


def test_ddl_rolls_back_with_its_transaction(tmp_path: Path) -> None:
    """A failed transaction undoes its DDL as well as its rows.

    Python's sqlite3 driver never opens a transaction for DDL on its own, so without the
    explicit BEGIN in `make_engine` this table outlives the rollback — and a migration
    that fails partway leaves the statements it already ran behind.
    """
    engine = make_engine(tmp_path / "t.db")
    create = text("CREATE TABLE half_applied (x INTEGER)")

    # Two statements, the second doomed — a migration failing on its second step.
    with contextlib.suppress(OperationalError), engine.begin() as connection:
        connection.execute(create)
        connection.execute(create)

    assert not inspect(engine).has_table("half_applied")


def test_create_all_is_idempotent(tmp_path: Path) -> None:
    """Calling create_all twice on the same engine does not error."""
    engine = make_engine(tmp_path / "t.db")
    create_all(engine)
    create_all(engine)


def test_exact_decimal_round_trips_high_precision_values(tmp_path: Path) -> None:
    """An ExactDecimal column round-trips a value past 2dp exactly, unlike Money."""
    engine = make_engine(tmp_path / "t.db")
    metadata = MetaData()
    t = Table(
        "t", metadata, Column("id", Integer, primary_key=True), Column("amount", ExactDecimal)
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(insert(t).values(id=1, amount=Decimal("0.923456")))
        got = conn.execute(select(t.c.amount)).scalar_one()

    assert got == Decimal("0.923456")
    assert isinstance(got, Decimal)


def test_exact_decimal_handles_none(tmp_path: Path) -> None:
    """An ExactDecimal column round-trips NULL as None."""
    engine = make_engine(tmp_path / "t.db")
    metadata = MetaData()
    t = Table(
        "t", metadata, Column("id", Integer, primary_key=True), Column("amount", ExactDecimal)
    )
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(insert(t).values(id=1, amount=None))
        assert conn.execute(select(t.c.amount)).scalar_one() is None


def test_upgrading_is_a_no_op_in_the_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Under wasm there is no alembic to import, so the call must return before trying.

    The Pyodide boot script used to monkeypatch this out; owning the condition here means
    the browser build cannot drift away from the app's own startup path. Blocking the
    import is what makes the assertion real — an empty database alone would not.
    """
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.setitem(sys.modules, "alembic", None)
    engine = make_engine(tmp_path / "wasm.db")
    upgrade_to_head(engine)
    assert inspect(engine).get_table_names() == []
