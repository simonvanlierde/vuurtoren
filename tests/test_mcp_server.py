"""Tests for the MCP tool functions, called in-process against a seeded temp database."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import date
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError
from sqlalchemy.orm import sessionmaker

from vuurtoren import mcp_server
from vuurtoren.api.deps import _engine
from vuurtoren.db import _MIGRATIONS, make_engine
from vuurtoren.seed import EXAMPLE_HOUSEHOLD_PATHS, load_household_spec, seed_household

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

START = "2026-01-01"


@pytest.fixture(autouse=True)
def seeded_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the app's default database at a seeded temp file, as the server would see it."""
    monkeypatch.setenv("VUURTOREN_DB", str(tmp_path / "mcp.db"))
    _engine.cache_clear()
    with sessionmaker(bind=_engine())() as session:
        seed_household(session, load_household_spec(EXAMPLE_HOUSEHOLD_PATHS[0]))
        session.commit()
    yield
    _engine.cache_clear()


def test_read_tools_return_the_seeded_household() -> None:
    """Each read tool answers with the rows the seed wrote."""
    assert len(mcp_server.get_households()) == 1
    assert mcp_server.get_people()
    assert mcp_server.get_accounts()
    assert isinstance(mcp_server.get_cash_flows(), list)
    assert isinstance(mcp_server.get_milestones(), list)
    assert mcp_server.get_scenarios()


def test_tax_config_reads_the_household_country() -> None:
    """Without a country the household's own is used; an unknown one is a tool error."""
    assert mcp_server.get_tax_config(2026)["fields"]
    with pytest.raises(ToolError, match="XX"):
        mcp_server.get_tax_config(2026, country="XX")


def test_project_inflation_override_moves_the_fi_date() -> None:
    """Higher inflation changes the answer; the headline numbers come back, not matrices."""
    baseline = mcp_server.project(start=START)
    high = mcp_server.project(start=START, inflation=0.06)
    assert baseline["fi_date"] != high["fi_date"]
    assert "net_worth" not in baseline


def test_project_equity_return_override_moves_end_net_worth() -> None:
    """An equity return override reaches the equity accounts."""
    baseline = mcp_server.project(start=START)
    low = mcp_server.project(start=START, equity_return=0.01)
    assert low["end_net_worth"] < baseline["end_net_worth"]


def test_project_rejects_a_bad_scenario() -> None:
    """An API error surfaces as the tool error carrying its detail."""
    with pytest.raises(ToolError, match="not found"):
        mcp_server.project(start=START, scenario_id=999)


def test_the_server_registers_read_tools_only() -> None:
    """Exactly the reviewed read tools: a new tool fails here until someone adds it on purpose.

    A prefix denylist let any `import_x` or `run_x` through.
    """
    names = {t.name for t in mcp_server.mcp._tool_manager.list_tools()}  # noqa: SLF001
    assert names == {
        "get_households",
        "get_people",
        "get_accounts",
        "get_cash_flows",
        "get_milestones",
        "get_scenarios",
        "get_tax_config",
        "project",
    }


def test_project_starts_this_local_month_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default start is the first of the local month, as the UI's.

    UTC was still the previous month for an hour or two after midnight on the 1st in
    Amsterdam.
    """

    class _March1(date):
        @classmethod
        def today(cls) -> _March1:
            return cls(2026, 3, 1)

    monkeypatch.setattr(mcp_server, "date", _March1, raising=False)
    assert mcp_server.project()["start"].startswith("2026-03")


def test_a_server_crash_reaches_the_client_as_a_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 500 with a plain-text body is still a ToolError, not a re-raised exception."""
    broken = FastAPI()

    @broken.get("/api/households")
    def _crash() -> None:
        msg = "boom"
        raise RuntimeError(msg)

    monkeypatch.setattr(mcp_server, "app", broken)
    with pytest.raises(ToolError, match="Internal Server Error"):
        mcp_server.get_households()


def test_a_locked_database_is_not_called_unmigrated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only a missing alembic_version table means never migrated; other errors say what failed."""

    def _locked(*_args: object, **_kwargs: object) -> sqlite3.Connection:
        msg = "database is locked"
        raise sqlite3.OperationalError(msg)

    monkeypatch.setattr(mcp_server.sqlite3, "connect", _locked)
    with pytest.raises(ToolError, match="database is locked"):
        mcp_server.get_households()


def test_an_api_error_reaches_the_client_with_its_detail() -> None:
    """A refused request reads as the API's reason, not the SDK's masked crash text."""
    call = mcp_server.mcp.call_tool("get_tax_config", {"year": 2026, "country": "ZZ"})
    with pytest.raises(ToolError) as excinfo:
        asyncio.run(call)
    assert not isinstance(excinfo.value, UnexpectedToolError)
    assert "ZZ" in str(excinfo.value)


def test_a_missing_database_is_not_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The server refuses to start a database; opening the app is what creates one."""
    missing = tmp_path / "absent.db"
    monkeypatch.setenv("VUURTOREN_DB", str(missing))
    _engine.cache_clear()
    with pytest.raises(ToolError, match="no vuurtoren database"):
        mcp_server.get_households()
    assert not missing.exists()


def test_an_older_database_is_not_upgraded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A database behind the script head stays at its revision, so v0.1.x can still open it."""
    old = tmp_path / "old.db"
    older = "7723b1f65327"  # the head v0.1.0 shipped
    engine = make_engine(old)
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, older)
    engine.dispose()
    monkeypatch.setenv("VUURTOREN_DB", str(old))
    _engine.cache_clear()
    with pytest.raises(ToolError, match="older vuurtoren"):
        mcp_server.get_households()
    with sqlite3.connect(old) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchall() == [(older,)]
