"""Tests for the MCP tool functions, called in-process against a seeded temp database."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.orm import sessionmaker

from vuurtoren import mcp_server
from vuurtoren.api.deps import _engine
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
    with pytest.raises(ValueError, match="XX"):
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
    with pytest.raises(ValueError, match="not found"):
        mcp_server.project(start=START, scenario_id=999)


def test_the_server_registers_read_tools_only() -> None:
    """No tool name suggests a write."""
    names = {t.name for t in mcp_server.mcp._tool_manager.list_tools()}  # noqa: SLF001
    assert names
    assert not {n for n in names if n.startswith(("create", "update", "delete", "set"))}
