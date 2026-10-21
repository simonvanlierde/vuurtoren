"""Tests for the FastAPI layer.

Every test drives a temp SQLite file through `TestClient` — no session, no fixture
that reaches into `vuurtoren.api`'s module-level engine. `get_session` is overridden
per test so the real `data/vuurtoren.db` default path is never touched.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect
from sqlalchemy.orm import sessionmaker

from vuurtoren import prices
from vuurtoren.api import _engine, app, get_session
from vuurtoren.db import create_all, make_engine
from vuurtoren.returns_data import START_YEARS
from vuurtoren.seed import EXAMPLE_HOUSEHOLD_PATHS, load_household_spec

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """Provide a TestClient backed by a temp SQLite file, isolated per test."""
    engine = make_engine(tmp_path / "test.db")
    create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def _override_get_session() -> Iterator[object]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _make_household(client: TestClient) -> int:
    resp = client.post("/api/households", json={"name": "Test Household"})
    assert resp.status_code == 201
    return resp.json()["id"]


ECB_XML_USD = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"'
    ' xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">'
    '<Cube><Cube time="2026-07-23"><Cube currency="USD" rate="1.0850"/></Cube></Cube>'
    "</gesmes:Envelope>"
)


# --- CRUD round-trips ---


def test_household_crud_roundtrip(client: TestClient) -> None:
    """A household round-trips through create, list, update and delete."""
    resp = client.post(
        "/api/households",
        json={"name": "Acme", "fiscal_partners": True, "life_expectancy_age": 90},
    )
    assert resp.status_code == 201
    household = resp.json()
    hh_id = household["id"]
    assert household["name"] == "Acme"
    assert household["fiscal_partners"] is True

    resp = client.get("/api/households")
    assert resp.status_code == 200
    assert [h["name"] for h in resp.json()] == ["Acme"]

    resp = client.put(f"/api/households/{hh_id}", json={"name": "Acme Renamed"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Acme Renamed"

    resp = client.delete(f"/api/households/{hh_id}")
    assert resp.status_code == 204
    assert client.get("/api/households").json() == []


def test_account_decimal_fidelity_roundtrip(client: TestClient) -> None:
    """Money never round-trips through a float (invariant 4 in CONTRIBUTING.md).

    A value with more precision than a float can carry exactly must come back
    byte-identical as a string.
    """
    hh_id = _make_household(client)
    resp = client.post(
        "/api/accounts",
        json={
            "household_id": hh_id,
            "name": "Brokerage",
            "kind": "equity",
            "tax_treatment": "nl.box3_investment",
            "manual_value": "12345.67",
            "cost_basis": "10000.01",
            "return_assumption": 0.06,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["manual_value"] == "12345.67"
    assert isinstance(body["manual_value"], str)
    assert body["cost_basis"] == "10000.01"

    # Raw response text must never contain an unquoted float for the money fields.
    assert '"manual_value":"12345.67"' in resp.text.replace(" ", "")

    account_id = body["id"]
    (stored,) = client.get("/api/accounts").json()
    assert stored["manual_value"] == "12345.67"

    resp = client.put(
        f"/api/accounts/{account_id}",
        json={
            "household_id": hh_id,
            "name": "Brokerage",
            "kind": "equity",
            "tax_treatment": "nl.box3_investment",
            "manual_value": "99999.99",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["manual_value"] == "99999.99"

    resp = client.delete(f"/api/accounts/{account_id}")
    assert resp.status_code == 204


def test_account_currency_round_trips_through_a_whole_object_put(client: TestClient) -> None:
    """PUT the account exactly as the UI does: the object it just read, currency changed.

    The read model carries an `id` the write model has no field for, so this also pins
    that the extra key is ignored rather than rejected.
    """
    hh_id = _make_household(client)
    account = client.post(
        "/api/accounts",
        json={
            "household_id": hh_id,
            "name": "US brokerage",
            "kind": "equity",
            "tax_treatment": "nl.box3_investment",
            "manual_value": "5000.00",
        },
    ).json()
    assert account["currency"] == "EUR"  # the default, so existing accounts are unaffected

    resp = client.put(f"/api/accounts/{account['id']}", json={**account, "currency": "USD"})
    assert resp.status_code == 200
    assert resp.json()["currency"] == "USD"
    assert resp.json()["manual_value"] == "5000.00"  # the rest of the object survived

    resp = client.put(f"/api/accounts/{account['id']}", json={**account, "currency": "XYZ"})
    assert resp.status_code == 422


def test_price_point_decimal_fidelity_and_uniqueness(client: TestClient) -> None:
    """A price point's decimals survive at full precision; a duplicate account+date is rejected."""
    hh_id = _make_household(client)
    account_id = client.post(
        "/api/accounts",
        json={
            "household_id": hh_id,
            "name": "ETF",
            "kind": "equity",
            "tax_treatment": "nl.box3_investment",
            "manual_value": "1000.00",
        },
    ).json()["id"]

    payload = {
        "account_id": account_id,
        "date": "2026-01-15",
        "price_native": "123.456789",
        "currency": "USD",
        "fx_rate_to_eur": "0.923456",
        "value_eur": "114.02",
        "source": "manual",
    }
    resp = client.post("/api/price-points", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    # ExactDecimal fields must survive with full precision, not quantised to cents.
    assert body["price_native"] == "123.456789"
    assert body["fx_rate_to_eur"] == "0.923456"
    assert body["value_eur"] == "114.02"

    # A second point for the same account+date violates the UNIQUE constraint.
    resp = client.post("/api/price-points", json=payload)
    assert resp.status_code == 409


def test_cash_flow_crud_roundtrip(client: TestClient) -> None:
    """A cash flow's Money amount round-trips as a string."""
    hh_id = _make_household(client)
    resp = client.post(
        "/api/cash-flows",
        json={
            "household_id": hh_id,
            "label": "Salary",
            "amount_monthly": "5000.00",
            "kind": "income",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["amount_monthly"] == "5000.00"


# --- discriminated-union validation on write ---


def test_milestone_with_unknown_type_is_rejected_with_422(client: TestClient) -> None:
    """An unknown milestone params type is rejected and never persisted."""
    hh_id = _make_household(client)
    resp = client.post(
        "/api/milestones",
        json={
            "household_id": hh_id,
            "label": "Bad milestone",
            "on_date": "2030-01-01",
            "params": {"type": "not_a_real_milestone_type", "amount": "100"},
        },
    )
    assert resp.status_code == 422

    # And it must not have persisted.
    assert client.get("/api/milestones").json() == []


def test_milestone_valid_params_roundtrip(client: TestClient) -> None:
    """A milestone's discriminated params round-trip by id."""
    hh_id = _make_household(client)
    resp = client.post(
        "/api/milestones",
        json={
            "household_id": hh_id,
            "label": "Windfall",
            "on_date": "2030-06-01",
            "params": {"type": "lump_sum_in", "amount": "5000.50"},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["params"]["type"] == "lump_sum_in"
    assert body["params"]["amount"] == "5000.50"

    (stored,) = client.get("/api/milestones").json()
    assert stored["id"] == body["id"]
    assert stored["params"]["amount"] == "5000.50"


def test_a_projection_refuses_accounts_tagged_for_the_old_tax_country(
    client: TestClient,
) -> None:
    """The household may switch country first; projecting before the retag is a 400.

    Account saves are checked against the household's current country, so the switch
    has to save while the accounts still carry `nl.*` keys. Projected like that, Austria
    taxed them as nothing.
    """
    hh_id = _seed_projectable_household(client)
    client.post(
        "/api/cash-flows",
        json={"household_id": hh_id, "label": "Living", "amount_monthly": "1500.00"},
    )
    resp = client.put(f"/api/households/{hh_id}", json={"name": "x", "tax_country": "AT"})
    assert resp.status_code == 200

    req = {"start": "2026-01-01"}
    for path, extra in (
        ("/api/project", {}),
        ("/api/sensitivity", {}),
        ("/api/sweep", {"knob": "monthly_spending", "points": 2, "n_runs": 2}),
    ):
        resp = client.post(path, json={**req, **extra})
        assert resp.status_code == 400, path
        detail = resp.json()["detail"]
        assert "Cash buffer (nl.box3_bank)" in detail
        assert "World equity (nl.box3_investment)" in detail

    retag = {"Cash buffer": "at.bank", "World equity": "at.investment"}
    for account in client.get("/api/accounts").json():
        put = client.put(
            f"/api/accounts/{account['id']}",
            json={**account, "tax_treatment": retag[account["name"]]},
        )
        assert put.status_code == 200
    assert client.post("/api/project", json=req).status_code == 200


@pytest.mark.parametrize(
    "body",
    [{"base_currency": "USD"}, {"tax_country": "ZZ"}],
    ids=["base_currency", "tax_country"],
)
def test_a_household_the_engine_cannot_run_is_refused_at_save(
    client: TestClient, body: dict[str, str]
) -> None:
    """Saved, either value broke every read and projection of the household with a 500."""
    resp = client.post("/api/households", json={"name": "x", **body})
    assert resp.status_code == 422
    hh_id = _make_household(client)
    assert client.put(f"/api/households/{hh_id}", json={"name": "x", **body}).status_code == 422
    assert client.get("/api/households").status_code == 200


def test_a_scenario_with_an_unknown_tax_field_is_refused_at_save(client: TestClient) -> None:
    """A typo'd tax figure saved cleanly, then every projection of the scenario was a 500."""
    hh_id = _make_household(client)
    resp = client.post(
        "/api/scenarios",
        json={
            "household_id": hh_id,
            "name": "bad",
            "overrides": {"tax": {"NL": {"2026": {"box3_rat": "0.40"}}}},
        },
    )
    assert resp.status_code == 422
    assert "box3_rat" in str(resp.json()["detail"])
    out_of_range = {"tax": {"NL": {"2026": {"box3_rate": "5"}}}}
    resp = client.post(
        "/api/scenarios", json={"household_id": hh_id, "name": "bad", "overrides": out_of_range}
    )
    assert resp.status_code == 422


def test_live_tax_overrides_with_an_unknown_field_are_a_400(client: TestClient) -> None:
    """The same check on a projection's own overrides, which are never saved."""
    _seed_projectable_household(client)
    resp = client.post(
        "/api/project",
        json={"start": "2026-01-01", "overrides": {"tax": {"NL": {"2026": {"bogus": "1"}}}}},
    )
    assert resp.status_code == 400
    assert "bogus" in resp.json()["detail"]


def test_scenario_with_malformed_overrides_shape_is_rejected_with_422(client: TestClient) -> None:
    """A scenario override that doesn't nest per-year is rejected and never persisted."""
    hh_id = _make_household(client)
    resp = client.post(
        "/api/scenarios",
        json={
            "household_id": hh_id,
            "name": "Bad scenario",
            "overrides": {"tax": "this-should-be-a-nested-object-not-a-string"},
        },
    )
    assert resp.status_code == 422
    assert client.get("/api/scenarios").json() == []


@pytest.mark.parametrize("key", ["milestones", "acounts"])
def test_scenario_with_an_unknown_overrides_key_is_rejected_with_422(
    client: TestClient, key: str
) -> None:
    """A stray overrides key fails loudly instead of being stored and ignored.

    `milestones` included: per-milestone patching was never built, so the key is unknown.
    """
    hh_id = _make_household(client)
    resp = client.post(
        "/api/scenarios",
        json={"household_id": hh_id, "name": "Typo", "overrides": {key: {"1": {"x": 1}}}},
    )
    assert resp.status_code == 422
    assert client.get("/api/scenarios").json() == []


def test_scenario_valid_overrides_roundtrip(client: TestClient) -> None:
    """A scenario's nested override values round-trip."""
    hh_id = _make_household(client)
    resp = client.post(
        "/api/scenarios",
        json={
            "household_id": hh_id,
            "name": "Box 3 at 40%",
            "overrides": {"tax": {"NL": {"2026": {"box3_rate": "0.40"}}}},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["overrides"]["tax"]["NL"]["2026"]["box3_rate"] == "0.40"


# --- /api/project ---


def _seed_projectable_household(client: TestClient) -> int:
    hh_id = _make_household(client)
    client.post(
        "/api/people",
        json={"household_id": hh_id, "name": "Alex", "birth_date": "1990-01-01"},
    )
    client.post(
        "/api/accounts",
        json={
            "household_id": hh_id,
            "name": "Cash buffer",
            "kind": "cash",
            "tax_treatment": "nl.box3_bank",
            "manual_value": "10000.00",
        },
    )
    client.post(
        "/api/accounts",
        json={
            "household_id": hh_id,
            "name": "World equity",
            "kind": "equity",
            "tax_treatment": "nl.box3_investment",
            "manual_value": "5000.00",
            "return_assumption": 0.05,
        },
    )
    return hh_id


def test_project_returns_a_projection(client: TestClient) -> None:
    """A deterministic /api/project run returns months, net worth and a fire number."""
    _seed_projectable_household(client)
    resp = client.post("/api/project", json={"start": "2026-01-01", "n_runs": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["months"][0] == "2026-01-01"
    # net_worth is (n_runs, n_months); run 0's opening balance is the seeded total.
    assert data["net_worth"][0][0] == pytest.approx(15000.0)
    assert "fire" in data
    assert "fire_number" in data["fire"]


def test_project_opens_on_the_latest_price_point(client: TestClient) -> None:
    """A stored price point, not manual_value, sets the account's opening balance.

    The latest one wins, as on the Accounts view; an account without one keeps its
    manual_value.
    """
    _seed_projectable_household(client)
    equity_id = next(a["id"] for a in client.get("/api/accounts").json() if a["kind"] == "equity")
    for on_date, value in (("2025-12-01", "6000.00"), ("2025-12-31", "7500.00")):
        resp = client.post(
            "/api/price-points",
            json={
                "account_id": equity_id,
                "date": on_date,
                "price_native": "1",
                "currency": "EUR",
                "fx_rate_to_eur": "1",
                "value_eur": value,
                "source": "manual",
            },
        )
        assert resp.status_code == 201
    data = client.post("/api/project", json={"start": "2026-01-01", "n_runs": 1}).json()
    assert data["net_worth"][0][0] == pytest.approx(10000.0 + 7500.0)


def test_project_reports_the_inflation_factor_series(client: TestClient) -> None:
    """The real-terms deflator rides along with every projection, one value per month."""
    _seed_projectable_household(client)
    data = client.post("/api/project", json={"start": "2026-01-01"}).json()
    assert len(data["inflation_factor"]) == len(data["months"])
    assert data["inflation_factor"][0] == 1.0


def test_bequest_floor_lowers_success_probability(client: TestClient) -> None:
    """min_end_net_worth narrows success to runs that also finish above the floor."""
    _seed_projectable_household(client)
    req = {"start": "2026-01-01", "n_runs": 64, "seed": 42}
    base = client.post("/api/project", json=req).json()
    floored = client.post("/api/project", json={**req, "min_end_net_worth": 1e12}).json()
    # Nobody ends a seeded starter household holding a trillion euros.
    assert floored["success_probability"] == 0.0
    assert floored["success_probability"] <= base["success_probability"]


def test_solve_success_goal_honours_the_bequest_floor(client: TestClient) -> None:
    """The success goal counts the floor the way /api/project does."""
    hh_id = _seed_projectable_household(client)
    client.post(
        "/api/cash-flows",
        json={
            "household_id": hh_id,
            "label": "Living",
            "amount_monthly": "1500",
            "kind": "expense",
        },
    )
    goal = {"type": "success_at_least", "probability": 0.5, "n_runs": 20}
    req = {"start": "2026-01-01", "knob": "monthly_spending"}
    plain = client.post("/api/solve", json={**req, "goal": goal}).json()
    floored = client.post(
        "/api/solve", json={**req, "goal": {**goal, "min_end_net_worth": 1e12}}
    ).json()
    assert plain["converged"]
    # No spending level leaves a trillion euros, so no level meets the goal.
    assert not floored["converged"]


def test_project_accepts_a_scenario_id(client: TestClient) -> None:
    """/api/project accepts a scenario_id alongside the household."""
    hh_id = _seed_projectable_household(client)
    scenario_id = client.post(
        "/api/scenarios", json={"household_id": hh_id, "name": "Baseline", "is_baseline": True}
    ).json()["id"]

    resp = client.post(
        "/api/project",
        json={"start": "2026-01-01", "n_runs": 1, "scenario_id": scenario_id},
    )
    assert resp.status_code == 200


def test_project_without_a_cash_account_is_a_400(client: TestClient) -> None:
    """/api/project rejects a household with no cash account."""
    hh_id = _make_household(client)
    client.post(
        "/api/people",
        json={"household_id": hh_id, "name": "Alex", "birth_date": "1990-01-01"},
    )
    resp = client.post("/api/project", json={"start": "2026-01-01"})
    assert resp.status_code == 400


def test_project_with_unknown_scenario_is_a_404(client: TestClient) -> None:
    """/api/project 404s for a scenario_id that doesn't exist."""
    _seed_projectable_household(client)
    resp = client.post("/api/project", json={"start": "2026-01-01", "scenario_id": 999})
    assert resp.status_code == 404


def test_project_historical_mode_round_trips(client: TestClient) -> None:
    """Historical mode returns the Monte Carlo band shape.

    It also echoes the seed and the mode that produced it.
    """
    _seed_projectable_household(client)
    resp = client.post(
        "/api/project",
        json={"start": "2026-01-01", "n_runs": 200, "seed": 42, "mode": "historical"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "historical"
    assert data["seed"] == 42
    assert set(data["bands"]) == {"p10", "p50", "p90"}
    assert "success_probability" in data


def test_project_historical_mode_at_one_run_is_a_400(client: TestClient) -> None:
    """The deterministic path has no business bootstrapping.

    Reject rather than silently ignore the mode.
    """
    _seed_projectable_household(client)
    resp = client.post(
        "/api/project", json={"start": "2026-01-01", "n_runs": 1, "mode": "historical"}
    )
    assert resp.status_code == 400


def test_project_sequential_mode_runs_one_path_per_start_year(client: TestClient) -> None:
    """Sequential mode: n_runs comes from the dataset, and every run is labelled."""
    _seed_projectable_household(client)
    resp = client.post(
        "/api/project",
        json={"start": "2026-01-01", "n_runs": 200, "mode": "sequential"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "sequential"
    # The request asked for 200; the data says 55. The data wins, and says so.
    assert data["n_runs"] == len(START_YEARS)
    assert data["start_years"] == list(START_YEARS)
    assert len(data["fire"]["fi_dates"]) == len(START_YEARS)
    assert data["seed"] is None  # no rng to seed
    assert set(data["bands"]) == {"p10", "p50", "p90"}


def test_project_sequential_mode_reproduces_without_a_seed(client: TestClient) -> None:
    """Deterministic by construction: two identical requests give identical bands."""
    _seed_projectable_household(client)
    body = {"start": "2026-01-01", "mode": "sequential"}
    a = client.post("/api/project", json=body).json()
    b = client.post("/api/project", json=body).json()
    assert a["bands"] == b["bands"]


def test_project_gaussian_mode_carries_no_start_years(client: TestClient) -> None:
    """start_years is sequential-only — a bootstrapped run has no calendar name."""
    _seed_projectable_household(client)
    data = client.post("/api/project", json={"start": "2026-01-01", "n_runs": 32, "seed": 3}).json()
    assert data["start_years"] is None


def test_project_monte_carlo_exposes_per_run_fi_dates(client: TestClient) -> None:
    """The Monte Carlo branch emits per-run FI dates — the FIRE-date histogram's data."""
    _seed_projectable_household(client)
    data = client.post("/api/project", json={"start": "2026-01-01", "n_runs": 32, "seed": 7}).json()
    assert len(data["fire"]["fi_dates"]) == 32


# --- /api/solve ---


def test_solve_rejects_a_goal_missing_its_fields(client: TestClient) -> None:
    """A fire_by goal without a year is a 400, not a bisection over None."""
    _seed_projectable_household(client)
    resp = client.post(
        "/api/solve",
        json={"start": "2026-01-01", "knob": "monthly_spending", "goal": {"type": "fire_by"}},
    )
    assert resp.status_code == 400


def test_solve_die_with_zero_finds_a_spending(client: TestClient) -> None:
    """net_worth_at with at_least=0 solves the spending that depletes the pot by the year."""
    hh_id = _seed_projectable_household(client)
    client.post(
        "/api/cash-flows",
        json={
            "household_id": hh_id,
            "label": "Living",
            "amount_monthly": "500.00",
            "kind": "expense",
        },
    )
    resp = client.post(
        "/api/solve",
        json={
            "start": "2026-01-01",
            "knob": "monthly_spending",
            "goal": {"type": "net_worth_at", "year": 2050, "at_least": 0},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["converged"]
    assert data["solved_monthly"] > 0


def test_solve_without_flows_of_the_knob_does_not_converge(client: TestClient) -> None:
    """A household with no contribution flows can't solve for contributions — declines."""
    _seed_projectable_household(client)
    resp = client.post(
        "/api/solve",
        json={
            "start": "2026-01-01",
            "knob": "monthly_contributions",
            "goal": {"type": "fire_by", "year": 2050},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["converged"] is False


def test_sweep_returns_a_curve_of_points(client: TestClient) -> None:
    """/api/sweep returns one point per swept spending level with a success value."""
    hh_id = _seed_projectable_household(client)
    client.post(
        "/api/cash-flows",
        json={
            "household_id": hh_id,
            "label": "Living",
            "amount_monthly": "500.00",
            "kind": "expense",
        },
    )
    resp = client.post(
        "/api/sweep",
        json={"start": "2026-01-01", "knob": "monthly_spending", "points": 5, "n_runs": 32},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["points"]) == 5
    assert all("success" in p and "monthly" in p for p in data["points"])


def test_project_reports_net_swr(client: TestClient) -> None:
    """The deterministic projection carries a net SWR at or below the gross assumption."""
    _seed_projectable_household(client)
    data = client.post("/api/project", json={"start": "2026-01-01"}).json()
    assert "net_swr" in data["fire"]
    assert data["fire"]["net_swr"] <= 0.04
    assert "investment_income" in data


# --- /api/export ---


def test_export_shape(client: TestClient) -> None:
    """Export returns every entity keyed by table name, with money fields as strings."""
    hh_id = _seed_projectable_household(client)
    client.post(
        "/api/milestones",
        json={
            "household_id": hh_id,
            "label": "Windfall",
            "on_date": "2030-01-01",
            "params": {"type": "lump_sum_in", "amount": "1000"},
        },
    )
    client.post("/api/scenarios", json={"household_id": hh_id, "name": "Baseline"})

    resp = client.get("/api/export")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {
        "version",
        "household",
        "people",
        "accounts",
        "price_points",
        "cash_flows",
        "milestones",
        "scenarios",
    }
    assert data["household"]["id"] == hh_id
    assert len(data["people"]) == 1
    assert len(data["accounts"]) == 2
    assert data["accounts"][0]["manual_value"] == "10000.00"
    assert len(data["milestones"]) == 1
    assert len(data["scenarios"]) == 1


def test_export_with_no_household_is_a_404(client: TestClient) -> None:
    """/api/export 404s when no household has been seeded."""
    resp = client.get("/api/export")
    assert resp.status_code == 404


# --- /api/import ---


def _seed_rich_household(client: TestClient) -> int:
    """A household exercising every foreign key an import must keep valid.

    Includes a milestone whose params carry a person id, a milestone whose params carry
    a cash-flow id, a scenario whose overrides are keyed by a cash-flow id, and a stored
    price point — the references a naive re-insert would break.
    """
    hh_id = _seed_projectable_household(client)  # one person, two accounts
    person_id = client.get("/api/people").json()[0]["id"]
    accounts = client.get("/api/accounts").json()
    cf_id = client.post(
        "/api/cash-flows",
        json={
            "household_id": hh_id,
            "label": "Salary",
            "amount_monthly": "3000",
            "kind": "income",
            "owner_person_id": person_id,
        },
    ).json()["id"]
    client.post(
        "/api/milestones",
        json={
            "household_id": hh_id,
            "label": "Retire",
            "age_person_id": person_id,
            "age_years": 67,
            "params": {"type": "retire", "person_id": person_id},
        },
    )
    client.post(
        "/api/milestones",
        json={
            "household_id": hh_id,
            "label": "Raise",
            "on_date": "2030-01-01",
            "params": {
                "type": "income_change",
                "cash_flow_id": cf_id,
                "new_amount_monthly": "3500",
            },
        },
    )
    client.post(
        "/api/scenarios",
        json={
            "household_id": hh_id,
            "name": "What if",
            "overrides": {"cash_flows": {str(cf_id): {"amount_monthly": "4000"}}},
        },
    )
    client.post(
        "/api/price-points/manual",
        json={"account_id": accounts[1]["id"], "date": "2026-06-01", "value": "5100"},
    )
    return hh_id


def _client_on(engine: Engine) -> TestClient:
    """Point the app at `engine` and return a TestClient — caller clears overrides."""
    factory = sessionmaker(bind=engine)

    def _override() -> Iterator[object]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    return TestClient(app)


def test_export_carries_a_version(client: TestClient) -> None:
    """The export document is versioned so it is a stable interchange, not a blob."""
    _seed_projectable_household(client)
    data = client.get("/api/export").json()
    assert data["version"] == 1


def test_import_round_trips_a_full_export(tmp_path: Path) -> None:
    """Export a rich household into a fresh database and get the same document back.

    Ids are preserved, so every foreign key — including those inside milestone params
    and scenario overrides — survives the trip untouched.
    """
    src = make_engine(tmp_path / "src.db")
    create_all(src)
    dst = make_engine(tmp_path / "dst.db")
    create_all(dst)

    try:
        source = _client_on(src)
        hh_id = _seed_rich_household(source)
        doc = source.get("/api/export").json()

        target = _client_on(dst)
        resp = target.post("/api/import", json=doc)
        assert resp.status_code == 201
        assert resp.json()["household_id"] == hh_id
        assert resp.json()["imported"]["milestones"] == 2

        assert target.get("/api/export").json() == doc
    finally:
        app.dependency_overrides.clear()


def test_import_into_a_populated_database_is_a_409(client: TestClient) -> None:
    """Preserving ids means a colliding id is refused, not silently merged."""
    _seed_projectable_household(client)
    doc = client.get("/api/export").json()
    resp = client.post("/api/import", json=doc)
    assert resp.status_code == 409


def test_import_accepts_a_0_1_0_export_with_an_empty_milestones_override(
    tmp_path: Path,
) -> None:
    """v0.1.0 wrote `"milestones": {}` into every scenario's overrides; import drops it."""
    src = make_engine(tmp_path / "src.db")
    create_all(src)
    dst = make_engine(tmp_path / "dst.db")
    create_all(dst)

    try:
        source = _client_on(src)
        _seed_rich_household(source)
        doc = source.get("/api/export").json()
        legacy = {
            **doc,
            "scenarios": [
                {**s, "overrides": {**s["overrides"], "milestones": {}}} for s in doc["scenarios"]
            ],
        }

        target = _client_on(dst)
        resp = target.post("/api/import", json=legacy)
        assert resp.status_code == 201, resp.json()
        assert target.get("/api/export").json() == doc
    finally:
        app.dependency_overrides.clear()


def test_import_refuses_a_non_empty_milestones_override(client: TestClient) -> None:
    """A per-milestone patch never ran, so import refuses it rather than drop it silently."""
    _seed_rich_household(client)
    doc = client.get("/api/export").json()
    doc["scenarios"][0]["overrides"]["milestones"] = {"1": {"on_date": "2030-01-01"}}
    client.delete(f"/api/households/{doc['household']['id']}/all")

    resp = client.post("/api/import", json=doc)
    assert resp.status_code == 422


def test_deleting_a_household_with_everything_empties_the_database_for_import(
    client: TestClient,
) -> None:
    """The way out of the example household: delete it and all it holds, then restore.

    The plain household DELETE refuses while rows still reference it, so this route
    removes the dependants too, and an import into the emptied database then succeeds.
    """
    hh_id = _seed_rich_household(client)
    doc = client.get("/api/export").json()

    resp = client.delete(f"/api/households/{hh_id}/all")
    assert resp.status_code == 204
    for path in ("households", "people", "accounts", "cash-flows", "milestones", "scenarios"):
        assert client.get(f"/api/{path}").json() == [], path
    assert client.get("/api/price-points").json() == []

    resp = client.post("/api/import", json=doc)
    assert resp.status_code == 201
    assert client.get("/api/export").json() == doc


def test_deleting_an_unknown_household_with_everything_is_a_404(client: TestClient) -> None:
    """An unknown id is a 404, not a silent no-op."""
    assert client.delete("/api/households/999/all").status_code == 404


def test_import_rejects_an_unknown_version(client: TestClient) -> None:
    """A document from a future format is refused rather than half-read."""
    _seed_projectable_household(client)
    doc = client.get("/api/export").json()
    doc["version"] = 999
    resp = client.post("/api/import", json=doc)
    assert resp.status_code == 422


def test_refresh_prices_reports_per_account_outcomes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route wires prices.refresh_prices to HTTP.

    Outcomes serialise with Decimal as a string, and a failed account is reported
    rather than failing the request. The refresh logic itself is covered in
    test_prices.py with injected fetchers.
    """
    _make_household(client)

    def fake_refresh(
        _session: object, _household_id: int, **_kw: object
    ) -> list[prices.RefreshOutcome]:
        return [
            prices.RefreshOutcome(1, "ETF", ok=True, value_eur=Decimal("1234.56")),
            prices.RefreshOutcome(2, "Fund", ok=False, error="Stooq is down"),
        ]

    monkeypatch.setattr(prices, "refresh_prices", fake_refresh)
    resp = client.post("/api/refresh-prices")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0] == {
        "account_id": 1,
        "account_name": "ETF",
        "ok": True,
        "value_eur": "1234.56",
        "error": None,
    }
    assert body[1]["ok"] is False
    assert "Stooq" in body[1]["error"]


def test_refresh_prices_needs_a_household(client: TestClient) -> None:
    """/api/refresh-prices 404s when no household exists yet."""
    assert client.post("/api/refresh-prices").status_code == 404


def test_manual_price_value_upserts_and_serializes(client: TestClient) -> None:
    """The route wires record_manual_price to HTTP and upserts on a same-day re-post."""
    hh_id = _make_household(client)
    account = client.post(
        "/api/accounts",
        json={
            "household_id": hh_id,
            "name": "Savings",
            "kind": "cash",
            "tax_treatment": "nl.box3_bank",
            "manual_value": "100.00",
        },
    ).json()
    resp = client.post(
        "/api/price-points/manual",
        json={"account_id": account["id"], "date": "2026-07-24", "value": "12345.67"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["value_eur"] == "12345.67"
    assert body["source"] == "manual"
    # same-day re-post upserts rather than duplicating (UNIQUE constraint path)
    resp = client.post(
        "/api/price-points/manual",
        json={"account_id": account["id"], "date": "2026-07-24", "value": "200.00"},
    )
    assert resp.status_code == 201
    points = [p for p in client.get("/api/price-points").json() if p["account_id"] == account["id"]]
    assert len(points) == 1
    assert points[0]["value_eur"] == "200.00"


def test_manual_price_requires_exactly_one_of_price_or_value(client: TestClient) -> None:
    """Both, neither, and an unknown account_id are rejected with 400/400/404."""
    hh_id = _make_household(client)
    account = client.post(
        "/api/accounts",
        json={"household_id": hh_id, "name": "S", "kind": "cash", "tax_treatment": "nl.box3_bank"},
    ).json()
    both = client.post(
        "/api/price-points/manual",
        json={"account_id": account["id"], "date": "2026-07-24", "price": "1", "value": "1"},
    )
    neither = client.post(
        "/api/price-points/manual", json={"account_id": account["id"], "date": "2026-07-24"}
    )
    assert both.status_code == 400
    assert neither.status_code == 400
    missing = client.post(
        "/api/price-points/manual", json={"account_id": 9999, "date": "2026-07-24", "value": "1"}
    )
    assert missing.status_code == 404


def test_manual_price_foreign_currency_converts_server_side(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A USD per-unit price posted through the route converts to EUR at the ECB rate."""
    monkeypatch.setattr("vuurtoren.prices._default_fetch_ecb", lambda: ECB_XML_USD)
    hh_id = _make_household(client)
    account = client.post(
        "/api/accounts",
        json={
            "household_id": hh_id,
            "name": "World ETF",
            "kind": "equity",
            "tax_treatment": "nl.box3_investment",
            "price_source": "stooq",
            "isin": "VT",
            "currency": "USD",
            "units": "10",
        },
    ).json()
    resp = client.post(
        "/api/price-points/manual",
        json={"account_id": account["id"], "date": "2026-07-24", "price": "98.90"},
    )
    assert resp.status_code == 201
    assert resp.json()["value_eur"] == "911.52"


def test_manual_price_returns_502_when_ecb_feed_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A foreign-currency manual price 502s with an ECB-mentioning detail when the feed is down."""

    def _dead_feed() -> str:
        msg = "connection refused"
        raise OSError(msg)

    monkeypatch.setattr("vuurtoren.prices._default_fetch_ecb", _dead_feed)
    hh_id = _make_household(client)
    account = client.post(
        "/api/accounts",
        json={
            "household_id": hh_id,
            "name": "World ETF",
            "kind": "equity",
            "tax_treatment": "nl.box3_investment",
            "currency": "USD",
            "units": "10",
        },
    ).json()
    resp = client.post(
        "/api/price-points/manual",
        json={"account_id": account["id"], "date": "2026-07-24", "price": "98.90"},
    )
    assert resp.status_code == 502
    assert "ECB" in resp.json()["detail"]


def test_project_applies_scenario_overrides_when_building_the_plan(client: TestClient) -> None:
    """The scenario seam: /api/project routes non-tax override groups through apply_scenario.

    Otherwise the engine would reject them.
    """
    hh_id = _seed_projectable_household(client)
    flow_id = client.post(
        "/api/cash-flows",
        json={
            "household_id": hh_id,
            "label": "rent",
            "amount_monthly": "1000.00",
            "kind": "expense",
            "inflation_linked": False,
        },
    ).json()["id"]
    scenario_id = client.post(
        "/api/scenarios",
        json={
            "household_id": hh_id,
            "name": "Rent nicer",
            "overrides": {"cash_flows": {str(flow_id): {"amount_monthly": "2000.00"}}},
        },
    ).json()["id"]
    base = client.post("/api/project", json={"start": "2026-01-01"}).json()
    alt = client.post(
        "/api/project", json={"start": "2026-01-01", "scenario_id": scenario_id}
    ).json()
    assert float(alt["net_worth"][0][-1]) < float(base["net_worth"][0][-1])


def test_project_applies_a_per_account_override(client: TestClient) -> None:
    """A per-account override reaches the projection instead of 400-ing (2026-07-28).

    The group that gates both the sensitivity tornado's return row and the allocation
    comparison; a higher assumed return must raise ending net worth.
    """
    hh_id = _seed_projectable_household(client)
    account_id = client.get("/api/accounts").json()[0]["id"]
    scenario_id = client.post(
        "/api/scenarios",
        json={
            "household_id": hh_id,
            "name": "Per-account tweak",
            "overrides": {"accounts": {str(account_id): {"return_assumption": 0.12}}},
        },
    ).json()["id"]

    base = client.post("/api/project", json={"start": "2026-01-01"})
    tweaked = client.post("/api/project", json={"start": "2026-01-01", "scenario_id": scenario_id})
    assert tweaked.status_code == 200
    assert tweaked.json()["net_worth"][0][-1] > base.json()["net_worth"][0][-1]


def test_project_rejects_a_per_account_override_for_an_unknown_id(client: TestClient) -> None:
    """An accounts override naming an id outside the plan is a 400, not a silent no-op."""
    hh_id = _seed_projectable_household(client)
    scenario_id = client.post(
        "/api/scenarios",
        json={
            "household_id": hh_id,
            "name": "Ghost account",
            "overrides": {"accounts": {"9999": {"return_assumption": 0.1}}},
        },
    ).json()["id"]
    resp = client.post("/api/project", json={"start": "2026-01-01", "scenario_id": scenario_id})
    assert resp.status_code == 400
    assert "unknown id" in resp.json()["detail"]


def test_project_rejects_an_account_override_with_an_unknown_treatment(
    client: TestClient,
) -> None:
    """A typo'd tax_treatment in an override is a 400, as it is on the account itself.

    Unchecked, it taxed the account under no rule at all: Box 3 silently fell to zero.
    """
    hh_id = _seed_projectable_household(client)
    account_id = client.get("/api/accounts").json()[0]["id"]
    resp = client.post(
        "/api/project",
        json={
            "start": "2026-01-01",
            "household_id": hh_id,
            "overrides": {"accounts": {str(account_id): {"tax_treatment": "nl.box3_investmnet"}}},
        },
    )
    assert resp.status_code == 400
    assert "nl.box3_investmnet" in resp.json()["detail"]


@pytest.mark.parametrize("n_runs", [0, -1, 10_001])
def test_project_rejects_an_out_of_range_run_count(client: TestClient, n_runs: int) -> None:
    """n_runs=0 divided by zero (a 500) and an unbounded one could exhaust memory."""
    _seed_projectable_household(client)
    resp = client.post("/api/project", json={"start": "2026-01-01", "n_runs": n_runs})
    assert resp.status_code == 422


def test_a_monte_carlo_projection_returns_bands_and_success_probability(
    client: TestClient,
) -> None:
    """n_runs > 1 responds with p10/p50/p90 bands and a success probability.

    It also reports the seed actually used — not 10,000 full rows of JSON.
    """
    _seed_projectable_household(client)
    resp = client.post("/api/project", json={"start": "2026-01-01", "n_runs": 64, "seed": 42})
    assert resp.status_code == 200
    data = resp.json()
    assert "net_worth" not in data
    assert set(data["bands"]) == {"p10", "p50", "p90"}
    assert len(data["bands"]["p50"]) == len(data["months"])
    assert 0.0 <= data["success_probability"] <= 1.0
    assert data["seed"] == 42
    again = client.post(
        "/api/project", json={"start": "2026-01-01", "n_runs": 64, "seed": 42}
    ).json()
    assert again["bands"]["p50"] == data["bands"]["p50"]


def test_a_monte_carlo_projection_without_a_seed_gets_one_assigned(client: TestClient) -> None:
    """A Monte Carlo run with no seed given still gets one assigned in the response."""
    _seed_projectable_household(client)
    data = client.post("/api/project", json={"start": "2026-01-01", "n_runs": 8}).json()
    assert isinstance(data["seed"], int)


def test_a_deterministic_projection_includes_flow_totals(client: TestClient) -> None:
    """A deterministic projection includes a total for each cash-flow kind."""
    _seed_projectable_household(client)
    data = client.post("/api/project", json={"start": "2026-01-01"}).json()
    assert set(data["flow_totals"]) == {"income", "expenses", "contributions", "housing"}


def test_the_tax_config_endpoint_serves_resolved_values_with_provenance(
    client: TestClient,
) -> None:
    """/api/tax-config serves resolved rates alongside their provenance status."""
    _make_household(client)
    resp = client.get("/api/tax-config", params={"year": 2026})
    assert resp.status_code == 200
    data = resp.json()
    assert data["country"] == "NL"
    box3 = data["fields"]["box3_rate"]
    assert box3["value"] == "0.36"
    assert box3["status"] == "final"
    assert box3["source"].startswith("http")
    assert data["fields"]["box3_forfait_bank"]["status"] == "provisional"
    assert data["fields"]["wwr_rate"]["status"] == "proposed"


def test_the_tax_config_endpoint_ships_each_figure_s_unit(client: TestClient) -> None:
    """The panel formats and range-checks from the `Money`/`Rate`/`Year` annotation.

    Re-deriving "is this a rate?" from field names in the client is what this avoids:
    the declaration next to the field already drives indexing and the range validator.
    """
    _make_household(client)
    data = client.get("/api/tax-config", params={"year": 2026}).json()
    assert data["currency"] == "EUR"
    assert data["fields"]["box3_rate"]["unit"] == "/1"
    assert data["fields"]["box3_allowance_per_person"]["unit"] == "currency"
    assert data["fields"]["regime_switch_year"]["unit"] == "year"


def test_meta_names_the_model_s_limits_for_the_household_s_country(client: TestClient) -> None:
    """/api/meta carries what the Plan surface needs to be judged honestly.

    Each limitation says which way it bends the answer, because a reader who knows the
    model omits something still cannot tell whether the omission flatters them.
    """
    _make_household(client)
    data = client.get("/api/meta").json()
    assert data["tax_country"] == "NL"
    assert len(data["limitations"]) >= 3
    for lim in data["limitations"]:
        assert lim["direction"] in {"understates", "overstates", "either"}
        assert lim["nl"]
        assert lim["en"]
        # Both locales written out, not one echoed into the other: these are tax terms
        # ("heffingskorting", "lijfrente") that stay Dutch inside otherwise-English prose.
        assert lim["nl"] != lim["en"]


def test_meta_marks_a_household_as_example_data_only_while_it_still_is(
    client: TestClient,
) -> None:
    """The "not your numbers" marker follows the data, not the build.

    It was gated on the Pyodide flag, so a visitor to a hosted server build read a
    stranger's figures with nothing saying so. Matching on names means it also switches
    off the moment they put their own in — which is when it should.
    """
    spec = load_household_spec(EXAMPLE_HOUSEHOLD_PATHS[0])
    hh_id = client.post("/api/households", json={"name": spec.household.name}).json()["id"]
    # One person short of the example: the marker must not fire on a partial match.
    for person in spec.people[:-1]:
        client.post(
            "/api/people",
            json={
                "household_id": hh_id,
                "name": person.name,
                "birth_date": person.birth_date.isoformat(),
            },
        )
    assert client.get("/api/meta").json()["example_data"] is False

    last = spec.people[-1]
    client.post(
        "/api/people",
        json={
            "household_id": hh_id,
            "name": last.name,
            "birth_date": last.birth_date.isoformat(),
        },
    )
    assert client.get("/api/meta").json()["example_data"] is True

    # Renaming the household is a visitor making it theirs, and the marker goes.
    renamed = client.put(
        f"/api/households/{hh_id}",
        json={"name": "Our Household", "base_currency": "EUR", "tax_country": "NL"},
    )
    assert renamed.status_code == 200
    assert client.get("/api/meta").json()["example_data"] is False


def test_the_tax_country_list_offers_residences_not_every_config(client: TestClient) -> None:
    """/api/tax-countries lists regimes, not `TAX_CONFIG`.

    The US figures are registered as a citizenship overlay's parameters. Offering "US"
    as a place to live would have handed the household editor an option that 404s the
    projection — which is the failure the select exists to prevent.
    """
    resp = client.get("/api/tax-countries")
    assert resp.status_code == 200
    assert resp.json() == ["AT", "NL"]


def test_project_accepts_live_tax_overrides(client: TestClient) -> None:
    """The tax panel's live editing path: `overrides.tax` without saving a scenario."""
    _seed_projectable_household(client)
    base = client.post("/api/project", json={"start": "2026-01-01"}).json()
    edited = client.post(
        "/api/project",
        json={
            "start": "2026-01-01",
            "overrides": {"tax": {"NL": {"2026": {"box3_allowance_per_person": "0"}}}},
        },
    ).json()
    assert edited["tax_paid"]["investment_tax"][0][0] > base["tax_paid"]["investment_tax"][0][0]


def test_a_plan_request_with_an_unknown_field_is_a_422(client: TestClient) -> None:
    """A stray field is refused, not ignored: `tax_overrides` would drop the tax edits."""
    _seed_projectable_household(client)
    tax = {"NL": {"2026": {"box3_rate": "0.40"}}}
    for path, extra in [
        ("/api/project", {}),
        ("/api/sensitivity", {}),
        ("/api/solve", {"knob": "monthly_spending", "goal": {"type": "fire_by", "year": 2050}}),
    ]:
        body = {"start": "2026-01-01", "tax_overrides": tax, **extra}
        assert client.post(path, json=body).status_code == 422, path


def test_inline_overrides_change_projection_without_persisting(client: TestClient) -> None:
    """A drafted milestone previews through /api/project and saves nothing."""
    hh_id = _seed_projectable_household(client)
    base = client.post("/api/project", json={"start": "2026-08-01"}).json()
    preview = client.post(
        "/api/project",
        json={
            "start": "2026-08-01",
            "overrides": {
                "added_milestones": [
                    {
                        "id": 0,
                        "household_id": hh_id,
                        "label": "windfall",
                        "on_date": "2027-01-01",
                        "params": {"type": "lump_sum_in", "amount": "100000"},
                    }
                ]
            },
        },
    ).json()
    assert preview["net_worth"][0][-1] > base["net_worth"][0][-1]
    assert client.get("/api/milestones").json() == []


def test_inline_overrides_are_mutually_exclusive_with_a_scenario(client: TestClient) -> None:
    """/api/project rejects overrides combined with scenario_id."""
    hh_id = _seed_projectable_household(client)
    scenario_id = client.post("/api/scenarios", json={"household_id": hh_id, "name": "S"}).json()[
        "id"
    ]
    resp = client.post(
        "/api/project",
        json={"start": "2026-08-01", "overrides": {}, "scenario_id": scenario_id},
    )
    assert resp.status_code == 400


def test_startup_migrates_before_the_first_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lifespan hook leaves a migrated database behind before any request arrives.

    Migrating on demand instead puts `alembic upgrade` on the request path, where
    concurrent first requests each run one and corrupt alembic's process-global state.
    """
    db_path = tmp_path / "startup.db"
    monkeypatch.setenv("VUURTOREN_DB", str(db_path))
    _engine.cache_clear()
    try:
        with TestClient(app):  # entering runs lifespan; no request is made inside
            tables = inspect(make_engine(db_path)).get_table_names()
    finally:
        _engine.cache_clear()

    assert "alembic_version" in tables
    assert "household" in tables


def test_sensitivity_ranks_the_assumptions(client: TestClient) -> None:
    """/api/sensitivity returns one bar per knob, widest first, each stating its delta."""
    _seed_projectable_household(client)
    resp = client.post("/api/sensitivity", json={"start": "2026-01-01", "metric": "end_net_worth"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["metric"] == "end_net_worth"
    assert body["baseline"] is not None
    knobs = [r["knob"] for r in body["rows"]]
    assert "inflation" in knobs
    assert all(r["delta"] > 0 for r in body["rows"])
    widths = [abs(r["high"] - r["low"]) for r in body["rows"] if r["low"] is not None]
    assert widths == sorted(widths, reverse=True)


def test_sensitivity_baseline_end_worth_is_in_real_terms(client: TestClient) -> None:
    """The zero line is the projection's last net worth in today's euros, like the bars."""
    _seed_projectable_household(client)
    req = {"start": "2026-01-01", "assumptions": {"inflation": 0.03}}
    projection = client.post("/api/project", json=req).json()
    real_end = projection["net_worth"][0][-1] / projection["inflation_factor"][-1]
    body = client.post("/api/sensitivity", json={**req, "metric": "end_net_worth"}).json()
    assert body["baseline"] == pytest.approx(real_end)


# --- FBAR / FATCA worksheet ---


def test_the_fbar_worksheet_is_empty_for_a_household_with_no_us_person(
    client: TestClient,
) -> None:
    """Not a 404 and not an error: "nobody here files" is an answer worth rendering."""
    _seed_projectable_household(client)

    resp = client.post(
        "/api/reporting/fbar",
        json={"start": "2026-01-01", "year": 2026, "usd_per_eur_override": "0.851"},
    )

    assert resp.status_code == 200
    assert resp.json()["worksheets"] == []


def test_the_fbar_worksheet_reports_a_us_persons_accounts_in_dollars(
    client: TestClient,
) -> None:
    """The whole worksheet end to end: peak during the year, at the year-end rate.

    The override stands in for the Treasury fetch, which no projected year has published —
    that is the normal case here, not a fault, and the endpoint says so when it is absent.
    """
    hh_id = _seed_projectable_household(client)
    person = client.post(
        "/api/people",
        json={
            "household_id": hh_id,
            "name": "Sam",
            "birth_date": "1990-01-01",
            "us_person": True,
            "us_filing_status": "single",
        },
    ).json()
    client.post(
        "/api/accounts",
        json={
            "household_id": hh_id,
            "name": "Dutch savings",
            "kind": "cash",
            "tax_treatment": "nl.box3_bank",
            "manual_value": "250000.00",
            "owner_person_id": person["id"],
        },
    )

    data = client.post(
        "/api/reporting/fbar",
        json={"start": "2026-01-01", "year": 2026, "usd_per_eur_override": "0.851"},
    ).json()

    assert data["rate"]["exchange_rate"] == "0.851"
    [sheet] = data["worksheets"]
    assert sheet["person_name"] == "Sam"
    # €250,000 divided by 0.851, not multiplied: dollars are the larger number.
    assert Decimal(sheet["aggregate_peak_usd"]) > Decimal(250_000)
    assert sheet["fbar_triggered"] is True
    assert sheet["fatca_triggered"] is True


def test_the_fbar_worksheet_refuses_a_year_outside_the_horizon(client: TestClient) -> None:
    """Reporting every threshold as uncrossed would be the worst possible answer."""
    hh_id = _seed_projectable_household(client)
    client.post(
        "/api/people",
        json={
            "household_id": hh_id,
            "name": "Sam",
            "birth_date": "1990-01-01",
            "us_person": True,
        },
    )

    resp = client.post(
        "/api/reporting/fbar",
        json={"start": "2026-01-01", "year": 1999, "usd_per_eur_override": "0.851"},
    )

    assert resp.status_code == 400
    assert "1999" in resp.json()["detail"]


@pytest.mark.parametrize("rate", ["0", "-1"])
def test_the_fbar_override_rate_must_be_positive(client: TestClient, rate: str) -> None:
    """Zero divided by nothing with a 500; a negative rate reported negative dollars."""
    hh_id = _seed_projectable_household(client)
    client.post(
        "/api/people",
        json={"household_id": hh_id, "name": "Sam", "birth_date": "1990-01-01", "us_person": True},
    )
    resp = client.post(
        "/api/reporting/fbar",
        json={"start": "2026-01-01", "year": 2026, "usd_per_eur_override": rate},
    )
    assert resp.status_code == 422


# --- early retirement ---


def _seed_retirable_household(client: TestClient) -> tuple[int, int]:
    """A projectable household plus a salary and living costs — retirement needs both."""
    hh_id = _seed_projectable_household(client)
    person_id = client.get("/api/people").json()[0]["id"]
    client.post(
        "/api/cash-flows",
        json={
            "household_id": hh_id,
            "owner_person_id": person_id,
            "label": "salary",
            "amount_monthly": "5000.00",
            "kind": "income",
        },
    )
    client.post(
        "/api/cash-flows",
        json={
            "household_id": hh_id,
            "label": "living",
            "amount_monthly": "2500.00",
            "kind": "expense",
        },
    )
    return hh_id, person_id


def test_retirement_solves_for_a_date(client: TestClient) -> None:
    """Mode 1: give a target probability, get the earliest date that clears it."""
    _, person_id = _seed_retirable_household(client)
    resp = client.post(
        "/api/retirement",
        json={
            "start": "2026-01-01",
            "person_ids": [person_id],
            "residual_monthly": "0",
            "probability": 0.85,
            "n_runs": 100,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["converged"] is True
    assert data["retire_date"] is not None
    # The 4%-rule date rides along so the UI can show both; they answer different
    # questions and are not required to agree.
    assert "fi_date" in data


def test_retirement_reports_odds_for_a_named_date(client: TestClient) -> None:
    """Mode 2: give the date, get the probability."""
    _, person_id = _seed_retirable_household(client)
    resp = client.post(
        "/api/retirement",
        json={
            "start": "2026-01-01",
            "person_ids": [person_id],
            "residual_monthly": "0",
            "at_date": "2040-01-01",
            "n_runs": 100,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["retire_date"] == "2040-01-01"
    assert 0.0 <= data["achieved"] <= 1.0


def test_retirement_needs_exactly_one_of_date_or_probability(client: TestClient) -> None:
    """Both or neither is a caller error, not a silently-picked default."""
    _, person_id = _seed_retirable_household(client)
    base = {"start": "2026-01-01", "person_ids": [person_id], "residual_monthly": "0"}
    assert client.post("/api/retirement", json=base).status_code == 400
    both = {**base, "at_date": "2040-01-01", "probability": 0.85}
    assert client.post("/api/retirement", json=both).status_code == 400


def test_retirement_barista_residual_beats_full_stop(client: TestClient) -> None:
    """A residual income makes the same date easier — the baristaFIRE claim, on the wire."""
    _, person_id = _seed_retirable_household(client)
    base = {
        "start": "2026-01-01",
        "person_ids": [person_id],
        "at_date": "2040-01-01",
        "n_runs": 100,
    }
    full = client.post("/api/retirement", json={**base, "residual_monthly": "0"}).json()
    barista = client.post("/api/retirement", json={**base, "residual_monthly": "1500"}).json()
    assert barista["achieved"] >= full["achieved"]


def test_the_monte_carlo_response_carries_the_mortality_overlay(client: TestClient) -> None:
    """Solvency and survival ride the same month grid, or the overlay cannot stack them.

    "Rich, broke or dead" needs both: how many runs are still solvent each
    month, and how likely the household is to be alive to see it.
    """
    _seed_projectable_household(client)
    data = client.post("/api/project", json={"start": "2026-01-01", "n_runs": 32, "seed": 3}).json()
    months = len(data["months"])
    assert len(data["solvent_fraction"]) == months
    assert len(data["survival"]) == months
    assert data["survival"][0] == pytest.approx(1.0)
    assert data["survival"][-1] < data["survival"][0]
    assert all(0.0 <= v <= 1.0 for v in data["solvent_fraction"])


def test_a_milestone_targeting_an_unknown_account_is_a_400(client: TestClient) -> None:
    """A bad target_account_id is a client error, not a KeyError halfway through the run."""
    hh_id = _seed_projectable_household(client)
    client.post(
        "/api/milestones",
        json={
            "household_id": hh_id,
            "label": "Inheritance",
            "on_date": "2030-01-01",
            "params": {"type": "lump_sum_in", "amount": "50000", "target_account_id": 999},
        },
    )
    resp = client.post("/api/project", json={"start": "2026-01-01", "n_runs": 1})
    assert resp.status_code == 400
    assert "999" in resp.json()["detail"]


def test_an_account_treatment_the_regime_does_not_know_is_rejected(client: TestClient) -> None:
    """A typo'd tax_treatment must fail at the boundary, not silently tax nothing."""
    hh_id = _make_household(client)
    body = {
        "household_id": hh_id,
        "name": "Brokerage",
        "kind": "equity",
        "tax_treatment": "nl.typo",
        "manual_value": "1000.00",
    }
    resp = client.post("/api/accounts", json=body)
    assert resp.status_code == 422
    assert "nl.typo" in resp.json()["detail"]

    good = client.post("/api/accounts", json={**body, "tax_treatment": "nl.box3_investment"})
    assert good.status_code == 201
    bad_update = client.put(f"/api/accounts/{good.json()['id']}", json=body)
    assert bad_update.status_code == 422


def test_an_account_without_a_tax_treatment_names_the_field(client: TestClient) -> None:
    """The field has no default: an omitted treatment is a field error, not an empty string.

    It used to default to `""`, which no regime lists, so every client that forgot the
    field got the regime's "not one the NL regime knows: [...]" sentence about a value it
    never sent. Required means pydantic names `tax_treatment` instead.
    """
    resp = client.post(
        "/api/accounts",
        json={
            "household_id": _make_household(client),
            "name": "Brokerage",
            "kind": "equity",
            "manual_value": "1000.00",
        },
    )
    assert resp.status_code == 422
    # A pydantic field error, not the regime's sentence about a value nobody sent.
    assert [d["loc"] for d in resp.json()["detail"]] == [["body", "tax_treatment"]]


def test_import_rejects_an_account_treatment_the_regime_does_not_know(client: TestClient) -> None:
    """Import writes accounts straight to the table, so it needs the same gate as create.

    Without it a typo'd treatment could not be saved through the drawer but could be
    restored from a document — and then taxed nothing at all.
    """
    _seed_projectable_household(client)
    doc = client.get("/api/export").json()
    doc["accounts"][0]["tax_treatment"] = "nl.typo"
    resp = client.post("/api/import", json=doc)
    assert resp.status_code == 422
    assert "nl.typo" in resp.json()["detail"]


@pytest.mark.parametrize(("kind", "value"), [("debt", "50000.00"), ("equity", "-1.00")])
def test_an_account_balance_with_the_wrong_sign_is_rejected(
    client: TestClient, kind: str, value: str
) -> None:
    """Debts are stored negative and everything else not, on create, update and import.

    The rule was checked only when seeding, so a loan entered as a positive amount
    saved, then failed Box 3 under NL and added to net worth under AT.
    """
    hh_id = _seed_projectable_household(client)
    account = {
        "household_id": hh_id,
        "name": "Loan",
        "kind": kind,
        "tax_treatment": "nl.box3_debt" if kind == "debt" else "nl.box3_investment",
        "manual_value": value,
    }
    assert client.post("/api/accounts", json=account).status_code == 422
    first = client.get("/api/accounts").json()[0]
    assert client.put(f"/api/accounts/{first['id']}", json=account).status_code == 422

    doc = client.get("/api/export").json()
    doc["accounts"][0] |= {"kind": kind, "manual_value": value}
    resp = client.post("/api/import", json=doc)
    assert resp.status_code == 422
    assert "Cash buffer" in str(resp.json()["detail"])


def test_a_pension_with_no_owner_and_no_unlock_date_is_rejected(client: TestClient) -> None:
    """Its unlock date comes from the owner's state-pension age, so it needs one of the two.

    Saved without either, it counted as liquid from the first month.
    """
    hh_id = _seed_projectable_household(client)
    pension = {
        "household_id": hh_id,
        "name": "Pension pot",
        "kind": "pension",
        "tax_treatment": "nl.box1_pension",
        "manual_value": "50000.00",
    }
    resp = client.post("/api/accounts", json=pension)
    assert resp.status_code == 422
    assert "liquid_from" in str(resp.json()["detail"])
    dated = client.post("/api/accounts", json={**pension, "liquid_from": "2057-01-01"})
    assert dated.status_code == 201


def test_a_contribution_with_no_target_account_is_rejected(client: TestClient) -> None:
    """A contribution moves cash into an account; with none named the money vanished."""
    hh_id = _seed_projectable_household(client)
    flow = {"household_id": hh_id, "label": "Invest", "amount_monthly": "500.00"}
    resp = client.post("/api/cash-flows", json={**flow, "kind": "contribution"})
    assert resp.status_code == 422
    assert "target_account_id" in str(resp.json()["detail"])
    assert client.post("/api/cash-flows", json={**flow, "kind": "expense"}).status_code == 201


def test_the_tax_config_endpoint_names_the_treatments_and_describes_each_field(
    client: TestClient,
) -> None:
    """The panel and the account drawer both read the country off one response.

    Without `valid_treatments` the drawer hardcodes an `nl.*` list, which is wrong the
    moment the household is Austrian; without `description` an ungrouped field has no
    label and is dropped from the panel entirely.
    """
    _make_household(client)
    for country, expected in (("NL", "nl.box3_investment"), ("AT", "at.investment_nonreporting")):
        data = client.get("/api/tax-config", params={"year": 2026, "country": country}).json()
        assert expected in data["valid_treatments"]
        assert data["valid_treatments"] == sorted(data["valid_treatments"])
        assert all(f["description"] for f in data["fields"].values())


def test_the_renamed_state_pension_assumption_still_accepts_the_old_name(
    client: TestClient,
) -> None:
    """A client written against `aow_growth_months_per_decade` must not start 422ing."""
    _seed_projectable_household(client)
    for name in ("aow_growth_months_per_decade", "state_pension_growth_months_per_decade"):
        resp = client.post(
            "/api/project",
            json={"start": "2026-01-01", "assumptions": {name: 6}},
        )
        assert resp.status_code == 200, resp.text


# --- local-server hardening ---


def test_a_foreign_host_header_is_refused(client: TestClient) -> None:
    """A DNS-rebound name reaching the loopback server gets 400, not the household."""
    resp = client.get("/api/households", headers={"Host": "attacker.example"})
    assert resp.status_code == 400
    assert client.get("/api/households", headers={"Host": "127.0.0.1:8000"}).status_code == 200
    assert client.get("/api/households", headers={"Host": "localhost:5173"}).status_code == 200


def test_a_cross_origin_write_is_refused(client: TestClient) -> None:
    """Another site's page cannot POST to the local server; the app's own origin can."""
    body = {"name": "From elsewhere"}
    foreign = client.post(
        "/api/households", json=body, headers={"Origin": "http://attacker.example"}
    )
    assert foreign.status_code == 403
    assert client.get("/api/households").json() == []
    own = client.post("/api/households", json=body, headers={"Origin": "http://testserver"})
    assert own.status_code == 201
    # Reads are not state-changing, and a request without Origin is not from a browser page.
    assert (
        client.get("/api/households", headers={"Origin": "http://attacker.example"}).status_code
        == 200
    )
    assert client.post("/api/households", json=body).status_code == 201
