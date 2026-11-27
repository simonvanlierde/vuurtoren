"""Read-only MCP server over the local API, on stdio.

Needs the `mcp` extra. Each tool calls the FastAPI app in-process (no socket is opened)
against the database `default_db_path` names, so the numbers are the ones the UI shows.
No tool changes your data: no POST-to-create, PUT or DELETE route is reachable. Opening the
app in-process does set the file to WAL mode and run an alembic no-op check at the current revision.
It never creates or upgrades a database either: the app's startup migration would, so a
tool call first checks the file exists and is already at the current schema revision.
"""

import sqlite3
from contextlib import closing
from datetime import date
from typing import Annotated, Any, Literal, TypedDict

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from vuurtoren.api import app
from vuurtoren.api.schemas import AssumptionsIn, SolveOut
from vuurtoren.db import _MIGRATIONS, default_db_path
from vuurtoren.tax.explanation import TaxExplanationOut

mcp = MCPServer("vuurtoren")
_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


class ScenarioDates(TypedDict):
    """The two dates to check when comparing a scenario."""

    scenario_id: int | None
    fi_date: str | None
    cash_shortfall: str | None


class ScenarioComparison(TypedDict):
    """Two deterministic projections with their shared inputs."""

    start: str
    assumptions: dict[str, Any]
    baseline: ScenarioDates
    scenario: ScenarioDates
    fi_months_delta: int | None


def _default_start() -> date:
    # The UI starts in the user's local month.
    return date.today().replace(day=1)  # noqa: DTZ011


def _require_current_db() -> None:
    """Refuse a missing or old database, which the app's lifespan would create or migrate."""
    path = default_db_path()
    if not path.is_file():
        msg = f"no vuurtoren database at {path}; open the app once to create it"
        raise ToolError(msg)
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS))
    head = ScriptDirectory.from_config(config).get_current_head()
    try:
        # closing(): a sqlite3 connection's own context manager commits but never closes.
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as conn:
            current = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.OperationalError as e:
        # Only a missing alembic_version table means never migrated; a locked or
        # unreadable file must not be sent to the upgrade advice.
        if "no such table" not in str(e):
            msg = f"cannot read the vuurtoren database at {path}: {e}"
            raise ToolError(msg) from e
        current = None
    if current is None or current[0] != head:
        msg = (
            "this database is from an older vuurtoren; open the app once to upgrade it "
            "(back it up first)"
        )
        raise ToolError(msg)


def _call(method: str, path: str, **kwargs: Any) -> Any:  # noqa: ANN401 -- JSON of any shape
    """Run one API request in-process; an error status becomes a tool error with its detail."""
    _require_current_db()
    # A server exception comes back as its 500 response instead of being re-raised here.
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.request(method, path, **kwargs)
    if resp.status_code >= 400:
        # ToolError, not ValueError: the SDK masks any other exception as a crash, so the
        # client would read only "Error executing tool" instead of the API's reason.
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:  # a plain-text body, such as the 500 page
            detail = resp.text
        raise ToolError(str(detail))
    return resp.json()


@mcp.tool()
def get_households() -> list[dict[str, Any]]:
    """The household: name, tax country, fiscal partners, life expectancy."""
    return _call("GET", "/api/households")


@mcp.tool()
def get_people() -> list[dict[str, Any]]:
    """The people in the household, with birth dates and retirement settings."""
    return _call("GET", "/api/people")


@mcp.tool()
def get_accounts() -> list[dict[str, Any]]:
    """Accounts with kind, tax treatment, value and assumed return."""
    return _call("GET", "/api/accounts")


@mcp.tool()
def get_cash_flows() -> list[dict[str, Any]]:
    """Income and expense flows."""
    return _call("GET", "/api/cash-flows")


@mcp.tool()
def get_milestones() -> list[dict[str, Any]]:
    """Dated life events (retire, buy a house, gifts, extra repayments)."""
    return _call("GET", "/api/milestones")


@mcp.tool()
def get_scenarios() -> list[dict[str, Any]]:
    """Saved scenarios and their overrides; pass an id to `project`."""
    return _call("GET", "/api/scenarios")


@mcp.tool()
def get_tax_config(year: int, country: str | None = None) -> dict[str, Any]:
    """The resolved tax figures for a year, each with its source and verification date.

    Country defaults to the household's.
    """
    params: dict[str, Any] = {"year": year}
    if country is not None:
        params["country"] = country
    return _call("GET", "/api/tax-config", params=params)


@mcp.tool()
def project(
    start: str | None = None,
    inflation: float | None = None,
    swr: float | None = None,
    house_appreciation: float | None = None,
    equity_return: float | None = None,
    scenario_id: int | None = None,
) -> dict[str, Any]:
    """Run the deterministic projection and return the headline numbers.

    Every argument is optional and unsaved. `start` is an ISO date (default: the first of
    this month). `inflation`, `swr`, `house_appreciation` and `equity_return` are yearly
    rates as fractions (0.03 is 3%); `equity_return` replaces the assumed return of every
    equity account. `scenario_id` applies a saved scenario and cannot be combined with
    `equity_return`. Returns the FI date (None if never reached), the FIRE number, and
    start and end net worth, both nominal and in start-date euros.
    """
    assumptions = {
        k: v
        for k, v in {
            "inflation": inflation,
            "swr": swr,
            "house_appreciation": house_appreciation,
        }.items()
        if v is not None
    }
    body: dict[str, Any] = {
        "start": start or _default_start().isoformat(),
        "assumptions": assumptions,
        "scenario_id": scenario_id,
    }
    if equity_return is not None:
        accounts = _call("GET", "/api/accounts")
        body["overrides"] = {
            "accounts": {
                a["id"]: {"return_assumption": equity_return}
                for a in accounts
                if a["kind"] == "equity"
            }
        }
    data = _call("POST", "/api/project", json=body)
    net_worth, factor = data["net_worth"][0], data["inflation_factor"]
    fire = data["fire"]
    return {
        "start": data["months"][0],
        "end": data["months"][-1],
        "fi_date": fire["fi_dates"][0],
        "coast_fire_date": fire["coast_fire_dates"][0],
        "fire_number": fire["fire_number"],
        "savings_rate": fire["savings_rate"],
        "net_swr": fire["net_swr"],
        "start_net_worth": net_worth[0],
        "end_net_worth": net_worth[-1],
        "end_net_worth_real": net_worth[-1] / factor[-1],
        "cash_shortfall": data["cash_shortfall"][0],
    }


def _scenario_dates(
    scenario_id: int | None, start: str, assumptions: dict[str, Any]
) -> ScenarioDates:
    data = _call(
        "POST",
        "/api/project",
        json={"start": start, "scenario_id": scenario_id, "assumptions": assumptions},
    )
    return {
        "scenario_id": scenario_id,
        "fi_date": data["fire"]["fi_dates"][0],
        "cash_shortfall": data["cash_shortfall"][0],
    }


@mcp.tool(annotations=_READ_ONLY)
def compare_scenarios(
    scenario_id: int,
    baseline_scenario_id: int | None = None,
    start: date | None = None,
    assumptions: AssumptionsIn | None = None,
) -> ScenarioComparison:
    """Compare a saved scenario with the base plan or another saved scenario.

    Use get_scenarios to find IDs. Omit baseline_scenario_id for the base plan.
    Both runs use the same start (default: first of this month) and assumptions.
    Annual rates are fractions (0.03 is 3%).
    A positive FI delta means the scenario reaches FI later.
    The delta is null if either run never reaches FI.
    Cash shortfall is the first month cash goes negative.
    """
    start_iso = (start or _default_start()).isoformat()
    shared_assumptions = (assumptions or AssumptionsIn()).model_dump(mode="json")
    baseline = _scenario_dates(baseline_scenario_id, start_iso, shared_assumptions)
    scenario = _scenario_dates(scenario_id, start_iso, shared_assumptions)
    baseline_fi, scenario_fi = baseline["fi_date"], scenario["fi_date"]
    delta = None
    if baseline_fi is not None and scenario_fi is not None:
        before, after = date.fromisoformat(baseline_fi), date.fromisoformat(scenario_fi)
        delta = (after.year - before.year) * 12 + after.month - before.month
    return {
        "start": start_iso,
        "assumptions": shared_assumptions,
        "baseline": baseline,
        "scenario": scenario,
        "fi_months_delta": delta,
    }


@mcp.tool(annotations=_READ_ONLY)
def solve_fi_target(
    target_year: Annotated[int, Field(ge=1, le=9999)],
    knob: Literal["monthly_spending", "monthly_contributions"] = "monthly_spending",
    scenario_id: int | None = None,
    start: date | None = None,
) -> SolveOut:
    """Find monthly spending or contributions in euros that reach FI by December of target_year.

    Start defaults to the first of this month. Omit scenario_id to use the base plan.
    Achieved is the projected FI year at the solved amount.
    If there is no solution in range, converged is false and solved_monthly is null.
    """
    body = {
        "start": (start or _default_start()).isoformat(),
        "scenario_id": scenario_id,
        "knob": knob,
        "goal": {"type": "fire_by", "year": target_year},
    }
    return SolveOut.model_validate(_call("POST", "/api/solve", json=body))


@mcp.tool(annotations=_READ_ONLY)
def explain_tax(
    year: int, scenario_id: int | None = None, start: date | None = None
) -> TaxExplanationOut:
    """Explain projected Dutch tax for one year, with calculation steps, sources and limits.

    The year must have a December assessment in the projection.
    Start defaults to the first of this month. Omit scenario_id to use the base plan.
    """
    body = {
        "start": (start or _default_start()).isoformat(),
        "scenario_id": scenario_id,
        "year": year,
    }
    return TaxExplanationOut.model_validate(_call("POST", "/api/tax-explanation", json=body))


def main() -> None:
    """Serve over stdio — the `vuurtoren-mcp` console script."""
    mcp.run("stdio")
