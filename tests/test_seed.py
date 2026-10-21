"""Seeding cash flows from the household TOML (the TOML is the bootstrap)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.orm import sessionmaker

from vuurtoren.db import create_all, make_engine
from vuurtoren.domain import CashFlowKind
from vuurtoren.seed import load_household_spec, main as seed_main, seed_household
from vuurtoren.tables import AccountRow, CashFlowRow, HouseholdRow

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

EXAMPLE_HOUSEHOLD = Path(__file__).parent.parent / "household.example.toml"


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    """Provide a Session backed by a temp SQLite file."""
    engine = make_engine(tmp_path / "seed.db")
    create_all(engine)
    with sessionmaker(engine)() as s:
        yield s


def test_example_household_seeds_all_three_cash_flow_kinds(session: Session) -> None:
    """Seeding the example household produces income, expense and contribution cash flows."""
    household_id = seed_household(session, load_household_spec(EXAMPLE_HOUSEHOLD))
    flows = (
        session.query(CashFlowRow).filter_by(household_id=household_id).order_by(CashFlowRow.id)
    ).all()
    kinds = [f.kind for f in flows]
    assert CashFlowKind.INCOME in kinds
    assert CashFlowKind.EXPENSE in kinds
    assert CashFlowKind.CONTRIBUTION in kinds


def test_contribution_target_resolves_to_the_named_account(session: Session) -> None:
    """A contribution cash flow's target_account_id resolves to an account in the same household."""
    household_id = seed_household(session, load_household_spec(EXAMPLE_HOUSEHOLD))
    contribution = (
        session.query(CashFlowRow)
        .filter_by(household_id=household_id, kind=CashFlowKind.CONTRIBUTION)
        .one()
    )
    target = session.get(AccountRow, contribution.target_account_id)
    assert target is not None
    assert target.household_id == household_id


def test_unknown_target_account_name_fails_loudly() -> None:
    """A contribution's target_account naming an account that doesn't exist is rejected."""
    spec = load_household_spec(EXAMPLE_HOUSEHOLD)
    data = spec.model_dump()
    data["cash_flows"][0]["target_account"] = "No such account"
    with pytest.raises(ValueError, match="No such account"):
        type(spec).model_validate(data)


def test_main_seeds_the_default_db_and_refuses_to_run_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`python -m vuurtoren.seed` seeds the app DB exactly once.

    A second run must refuse rather than duplicate the household.
    """
    monkeypatch.setenv("VUURTOREN_DB", str(tmp_path / "app.db"))
    monkeypatch.setenv("VUURTOREN_HOUSEHOLD", str(EXAMPLE_HOUSEHOLD))
    seed_main()

    engine = make_engine(tmp_path / "app.db")
    with sessionmaker(engine)() as s:
        assert s.query(HouseholdRow).count() == 1

    with pytest.raises(SystemExit):
        seed_main()
    with sessionmaker(engine)() as s:
        assert s.query(HouseholdRow).count() == 1


def test_a_positive_debt_fails_loudly() -> None:
    """The same sign rule as the API: a DEBT account is stored negative."""
    spec = load_household_spec(EXAMPLE_HOUSEHOLD)
    data = spec.model_dump()
    debt = data["accounts"][0]
    debt["kind"] = "debt"
    debt["manual_value"] = abs(debt["manual_value"]) + 1
    with pytest.raises(ValueError, match=debt["name"]):
        type(spec).model_validate(data)
