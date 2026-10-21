"""Tests for the ORM row layer: seeding, to_domain conversion and DB-level constraints."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from vuurtoren.db import create_all, make_engine
from vuurtoren.domain import Account, AccountKind, BuyProperty, Household
from vuurtoren.seed import HouseholdSpec, load_household_spec, seed_household
from vuurtoren.tables import (
    AccountRow,
    HouseholdRow,
    MilestoneRow,
    PersonRow,
    PricePointRow,
    ScenarioRow,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

EXAMPLE_HOUSEHOLD = Path(__file__).parent.parent / "household.example.toml"


@pytest.fixture
def household_spec() -> HouseholdSpec:
    """Load the committed example household spec."""
    return load_household_spec(EXAMPLE_HOUSEHOLD)


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    """Provide a Session backed by a temp SQLite file."""
    engine = make_engine(tmp_path / "t.db")
    create_all(engine)
    with sessionmaker(engine)() as s:
        yield s


def test_seed_creates_the_household_from_the_spec(
    session: Session, household_spec: HouseholdSpec
) -> None:
    """Seeding creates one account row per spec account, owned by the new household."""
    household_id = seed_household(session, household_spec)

    rows = session.query(AccountRow).all()
    assert len(rows) == 4
    assert all(r.household_id == household_id for r in rows)

    equity = next(r for r in rows if r.isin == "NL0000000000")
    assert equity.kind is AccountKind.EQUITY
    assert equity.tax_treatment == "nl.box3_investment"
    assert equity.manual_value == Decimal("50000.00")

    pension = next(r for r in rows if r.kind is AccountKind.PENSION)
    assert pension.tax_treatment == "nl.box1_pension"
    assert pension.liquid_from is not None


def test_to_domain_produces_frozen_value_objects(
    session: Session, household_spec: HouseholdSpec
) -> None:
    """AccountRow.to_domain() produces a frozen Account with the row's fields."""
    seed_household(session, household_spec)
    row = session.query(AccountRow).filter_by(isin="NL0000000000").one()
    account = row.to_domain()
    assert isinstance(account, Account)
    assert account.tax_treatment == "nl.box3_investment"
    assert account.manual_value == Decimal("50000.00")


def test_household_to_domain_carries_the_tax_country(
    session: Session, household_spec: HouseholdSpec
) -> None:
    """HouseholdRow.to_domain() carries the tax_country field through."""
    household_id = seed_household(session, household_spec)
    row = session.get(HouseholdRow, household_id)
    assert row is not None
    domain = row.to_domain()
    assert isinstance(domain, Household)
    assert domain.tax_country == "NL"


def test_milestone_params_round_trip_through_the_json_column(
    session: Session, household_spec: HouseholdSpec
) -> None:
    """A milestone's discriminated params round-trip through the JSON column and back."""
    household_id = seed_household(session, household_spec)
    session.add(
        MilestoneRow(
            household_id=household_id,
            label="Buy house",
            on_date=date(2028, 6, 1),
            params={
                "type": "buy_property",
                "price": "360000",
                "mortgage": "340000",
                "annual_rate": "0.042",
                "term_months": 360,
            },
        )
    )
    session.commit()

    row = session.query(MilestoneRow).one()
    milestone = row.to_domain()
    assert isinstance(milestone.params, BuyProperty)
    assert milestone.params.price == Decimal(360000)


def test_a_stored_milestone_with_a_bad_payload_fails_on_read(
    session: Session, household_spec: HouseholdSpec
) -> None:
    """Bad data can only arrive by hand-editing the DB; it must fail loudly, not silently."""
    household_id = seed_household(session, household_spec)
    session.add(
        MilestoneRow(
            household_id=household_id,
            label="Broken",
            on_date=date(2028, 6, 1),
            params={"type": "buy_property", "price": "not a number"},
        )
    )
    session.commit()
    row = session.query(MilestoneRow).one()
    with pytest.raises(ValidationError):
        row.to_domain()


def test_price_point_is_unique_per_account_and_date(
    session: Session, household_spec: HouseholdSpec
) -> None:
    """A second price point for the same account and date violates the UNIQUE constraint."""
    seed_household(session, household_spec)
    account = session.query(AccountRow).first()
    assert account is not None
    for _ in range(2):
        session.add(
            PricePointRow(
                account_id=account.id,
                date=date(2026, 7, 1),
                price_native=Decimal(100),
                currency="EUR",
                fx_rate_to_eur=Decimal(1),
                value_eur=Decimal(100),
                source="manual",
            )
        )
    with pytest.raises(IntegrityError):
        session.commit()


def test_price_point_stores_native_price_and_fx_rate_exactly(
    session: Session, household_spec: HouseholdSpec
) -> None:
    """ExactDecimal columns store price_native and fx_rate_to_eur at full precision."""
    seed_household(session, household_spec)
    account = session.query(AccountRow).first()
    assert account is not None
    price_native = Decimal("118.42751234567891")
    fx_rate = Decimal("0.9234567891234")
    session.add(
        PricePointRow(
            account_id=account.id,
            date=date(2026, 7, 1),
            price_native=price_native,
            currency="USD",
            fx_rate_to_eur=fx_rate,
            value_eur=Decimal("109.38"),
            source="manual",
        )
    )
    session.commit()

    row = session.query(PricePointRow).one()
    assert row.price_native == price_native
    assert row.fx_rate_to_eur == fx_rate


def test_account_stores_units_exactly(session: Session, household_spec: HouseholdSpec) -> None:
    """The ExactDecimal units column stores a fractional unit count at full precision."""
    household_id = seed_household(session, household_spec)
    units = Decimal("123.4567890123456789")
    added = AccountRow(household_id=household_id, units=units)
    session.add(added)
    session.commit()
    session.expire_all()

    row = session.get(AccountRow, added.id)
    assert row is not None
    assert row.units == units


def test_scenario_overrides_round_trip(session: Session, household_spec: HouseholdSpec) -> None:
    """A scenario's nested JSON overrides round-trip, with the year key as an int."""
    household_id = seed_household(session, household_spec)
    session.add(
        ScenarioRow(
            household_id=household_id,
            name="Box 3 at 40%",
            is_baseline=False,
            overrides={"tax": {"NL": {"2028": {"box3_rate": "0.40"}}}},
        )
    )
    session.commit()
    row = session.query(ScenarioRow).filter_by(name="Box 3 at 40%").one()
    assert row.to_domain().overrides.tax["NL"][2028]["box3_rate"] == Decimal("0.40")


def test_the_baseline_scenario_is_seeded(session: Session, household_spec: HouseholdSpec) -> None:
    """Seeding a household also creates exactly one baseline scenario."""
    seed_household(session, household_spec)
    assert session.query(ScenarioRow).filter_by(is_baseline=True).count() == 1


def test_load_household_spec_rejects_an_unknown_account_kind(tmp_path: Path) -> None:
    """An account kind outside the CASH|EQUITY|BOND|REAL_ESTATE|PENSION|DEBT set is rejected."""
    bad = tmp_path / "household.toml"
    bad.write_text(
        """
        [household]
        name = "Bad Household"

        [[people]]
        name = "Alex"
        birth_date = 1990-01-01

        [[accounts]]
        name = "Mystery account"
        owner = "Alex"
        kind = "crypto"
        tax_treatment = "nl.box3_investment"
        manual_value = "1000.00"
        """
    )
    with pytest.raises(ValidationError):
        load_household_spec(bad)


def test_load_household_spec_raises_a_helpful_error_when_the_file_is_missing(
    tmp_path: Path,
) -> None:
    """A missing household file raises FileNotFoundError naming the example to copy from."""
    missing = tmp_path / "does-not-exist.toml"
    with pytest.raises(FileNotFoundError, match=re.escape("household.example.toml")):
        load_household_spec(missing)


def test_load_household_spec_rejects_a_typo_d_tax_treatment(tmp_path: Path) -> None:
    """A tax_treatment typo is rejected, naming the offending account."""
    bad = tmp_path / "household.toml"
    bad.write_text(
        """
        [household]
        name = "Bad Household"

        [[people]]
        name = "Alex"
        birth_date = 1990-01-01

        [[accounts]]
        name = "Mystery account"
        owner = "Alex"
        kind = "equity"
        tax_treatment = "nl.box3_investments"
        manual_value = "1000.00"
        """
    )
    with pytest.raises(ValidationError, match="Mystery account"):
        load_household_spec(bad)


def test_load_household_spec_rejects_an_unknown_tax_country(tmp_path: Path) -> None:
    """A tax_country the app doesn't support is rejected, naming the bad value."""
    bad = tmp_path / "household.toml"
    bad.write_text(
        """
        [household]
        name = "Bad Household"
        tax_country = "XX"

        [[people]]
        name = "Alex"
        birth_date = 1990-01-01

        [[accounts]]
        name = "Mystery account"
        owner = "Alex"
        kind = "equity"
        tax_treatment = "nl.box3_investment"
        manual_value = "1000.00"
        """
    )
    with pytest.raises(ValidationError, match="XX"):
        load_household_spec(bad)


def test_load_household_spec_rejects_a_debt_account_with_a_positive_balance(
    tmp_path: Path,
) -> None:
    """A DEBT account must carry a negative balance; a positive one is rejected by name."""
    bad = tmp_path / "household.toml"
    bad.write_text(
        """
        [household]
        name = "Bad Household"

        [[people]]
        name = "Alex"
        birth_date = 1990-01-01

        [[accounts]]
        name = "Mortgage"
        owner = "Alex"
        kind = "debt"
        tax_treatment = "nl.box3_debt"
        manual_value = "50000.00"
        """
    )
    with pytest.raises(ValidationError, match="Mortgage"):
        load_household_spec(bad)


def test_load_household_spec_rejects_a_non_debt_account_with_a_negative_balance(
    tmp_path: Path,
) -> None:
    """A non-DEBT account with a negative balance is rejected, naming the account."""
    bad = tmp_path / "household.toml"
    bad.write_text(
        """
        [household]
        name = "Bad Household"

        [[people]]
        name = "Alex"
        birth_date = 1990-01-01

        [[accounts]]
        name = "Broker account"
        owner = "Alex"
        kind = "equity"
        tax_treatment = "nl.box3_investment"
        manual_value = "-1000.00"
        """
    )
    with pytest.raises(ValidationError, match="Broker account"):
        load_household_spec(bad)


def test_load_household_spec_accepts_a_debt_account_with_a_negative_balance(
    tmp_path: Path,
) -> None:
    """A DEBT account with a negative balance loads without complaint."""
    ok = tmp_path / "household.toml"
    ok.write_text(
        """
        [household]
        name = "Good Household"

        [[people]]
        name = "Alex"
        birth_date = 1990-01-01

        [[accounts]]
        name = "Mortgage"
        owner = "Alex"
        kind = "debt"
        tax_treatment = "nl.box3_debt"
        manual_value = "-50000.00"
        """
    )
    spec = load_household_spec(ok)
    assert spec.accounts[0].manual_value == Decimal("-50000.00")


def test_load_household_spec_accepts_the_example_household(household_spec: HouseholdSpec) -> None:
    """The committed household.example.toml itself loads and validates."""
    assert household_spec.household.name == "Example Household"
    assert len(household_spec.accounts) == 4


def test_person_to_domain_round_trips_every_column(
    session: Session, household_spec: HouseholdSpec
) -> None:
    """Every mapped column must reach the domain model with its value intact.

    PersonRow hand-listed its fields rather than using AccountRow's comprehension, so a
    new column was silently dropped unless something checked. Asserting on values rather
    than on key presence is the point: `model_dump()` emits every declared field whether
    or not `to_domain` populated it, so a key-presence check passes against the bug.
    """
    household_id = seed_household(session, household_spec)
    row = PersonRow(
        household_id=household_id,
        name="A",
        birth_date=date(1990, 1, 1),
        tax_residence="NL",
        pension_age_override="67y3m",
        us_person=True,
        us_filing_status="married_filing_separately",
    )
    session.add(row)
    session.flush()

    person = row.to_domain()

    for column in PersonRow.__table__.columns:
        assert getattr(person, column.name) == getattr(row, column.name), (
            f"to_domain() dropped or altered {column.name!r}"
        )


def test_us_person_fields_round_trip(session: Session, household_spec: HouseholdSpec) -> None:
    """Citizenship taxation is per person, so the flag and its filing status must persist."""
    household_id = seed_household(session, household_spec)
    row = PersonRow(
        household_id=household_id,
        name="A",
        birth_date=date(1990, 1, 1),
        tax_residence="NL",
        us_person=True,
        us_filing_status="married_filing_separately",
    )
    session.add(row)
    session.flush()

    person = row.to_domain()

    assert person.us_person is True
    assert person.us_filing_status == "married_filing_separately"


def test_account_overlay_treatment_round_trips(
    session: Session, household_spec: HouseholdSpec
) -> None:
    """A retained US brokerage account carries a residence key and an overlay key."""
    household_id = seed_household(session, household_spec)
    row = AccountRow(
        household_id=household_id,
        name="Schwab",
        kind=AccountKind.EQUITY,
        tax_treatment="nl.box3_investment",
        overlay_treatment="us.non_pfic",
    )
    session.add(row)
    session.flush()

    account = row.to_domain()

    assert account.tax_treatment == "nl.box3_investment"
    assert account.overlay_treatment == "us.non_pfic"
