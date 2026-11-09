"""Read-only MCP server over the local API, on stdio.

Needs the `mcp` extra. Each tool calls the FastAPI app in-process (no socket is opened)
against the database `default_db_path` names, so the numbers are the ones the UI shows.
Nothing here writes: no POST-to-create, PUT or DELETE route is reachable from a tool.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from vuurtoren.api import app

mcp = MCPServer("vuurtoren")


def _call(method: str, path: str, **kwargs: Any) -> Any:  # noqa: ANN401 -- JSON of any shape
    """Run one API request in-process; an error status becomes a tool error with its detail."""
    with TestClient(app) as client:
        resp = client.request(method, path, **kwargs)
    if resp.status_code >= 400:
        # ToolError, not ValueError: the SDK masks any other exception as a crash, so the
        # client would read only "Error executing tool" instead of the API's reason.
        raise ToolError(str(resp.json().get("detail", resp.text)))
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
        "start": start or datetime.now(UTC).date().replace(day=1).isoformat(),
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


def main() -> None:
    """Serve over stdio — the `vuurtoren-mcp` console script."""
    mcp.run("stdio")
