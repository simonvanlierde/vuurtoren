"""Seed a household into the database from a TOML household spec.

The spec's shape lives in ``household.example.toml`` at the repo root (committed,
fictional data). The real household goes in ``data/household.toml``, which is
gitignored and never committed -- see ``_default_household_path`` below.
"""

import os
import sys
import tomllib
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.orm import sessionmaker

from vuurtoren.db import default_db_path, make_engine, upgrade_to_head
from vuurtoren.domain import (
    AccountKind,
    CashFlowKind,
    Currency,
    FilingStatus,
    PriceSource,
    check_balance_sign,
)
from vuurtoren.tables import AccountRow, CashFlowRow, HouseholdRow, PersonRow, ScenarioRow
from vuurtoren.tax.regime import regime_for

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

DEFAULT_HOUSEHOLD_PATH = Path("data/household.toml")

# Where the committed fictional household can be found at runtime: the repo root for a
# checkout, /assets for the Pyodide build, which mounts it there. Neither existing is a
# legitimate answer (an installed wheel ships no example), and `is_example_household`
# then reports False — under-claiming beats labelling somebody's real data as a demo.
EXAMPLE_HOUSEHOLD_PATHS = (Path("household.example.toml"), Path("/assets/household.example.toml"))


def is_example_household(session: Session) -> bool:
    """Whether the stored household is still the committed fictional one.

    Matched on names rather than recorded at seed time, so it needs no column and no
    migration — and it stops being true the moment a visitor puts their own name in,
    which is exactly when a "these are not your numbers" marker should disappear.
    """
    household = session.query(HouseholdRow).order_by(HouseholdRow.id).first()
    if household is None:
        return False
    path = next((p for p in EXAMPLE_HOUSEHOLD_PATHS if p.exists()), None)
    if path is None:
        return False
    spec = load_household_spec(path)
    if household.name != spec.household.name:
        return False
    stored = sorted(p.name for p in session.query(PersonRow).all())
    return stored == sorted(p.name for p in spec.people)


class _StrictModel(BaseModel):
    """extra='forbid' so a typo'd field name in the TOML fails loudly, not silently."""

    model_config = ConfigDict(extra="forbid")


class HouseholdInfo(_StrictModel):
    """The `[household]` table of the TOML spec."""

    name: str = "Household"
    tax_country: str = "NL"
    fiscal_partners: bool = False
    life_expectancy_age: int = 95


class PersonSpec(_StrictModel):
    """One `[[people]]` entry."""

    name: str
    birth_date: date
    tax_residence: str = "NL"
    us_person: bool = False
    us_filing_status: FilingStatus | None = None
    """Citizenship, not residence — the two are separate fields because the United States
    taxes by the first and everyone else by the second."""


class AccountSpec(_StrictModel):
    """One `[[accounts]]` entry. DEBT accounts carry a negative `manual_value`."""

    name: str
    owner: str | None = None  # by person NAME -- ids are a DB concern
    kind: AccountKind
    tax_treatment: str
    overlay_treatment: str | None = None
    """Citizenship-scoped, and validated against the overlay rather than the regime — the
    two vocabularies must not read each other (invariant #2)."""
    isin: str | None = None
    price_source: PriceSource = PriceSource.MANUAL
    currency: Currency = "EUR"
    units: Decimal | None = None
    """Units held. A fetched-price account needs it: a refresh values it as units x price."""
    manual_value: Decimal
    cost_basis: Decimal | None = None
    return_assumption: float = 0.0
    distribution_yield: float = 0.0
    fund_realized_gain_yield: float = 0.0
    volatility_assumption: float = 0.0
    liquid_from: date | None = None

    @model_validator(mode="after")
    def _balance_sign(self) -> AccountSpec:
        check_balance_sign(self.name, self.kind, self.manual_value)
        return self


class CashFlowSpec(_StrictModel):
    """One `[[cash_flows]]` entry."""

    label: str
    amount_monthly: Decimal
    kind: CashFlowKind
    owner: str | None = None  # by person NAME, like AccountSpec.owner
    target_account: str | None = None  # by account NAME -- ids are a DB concern
    start_date: date | None = None
    end_date: date | None = None
    inflation_linked: bool = True


class HouseholdSpec(_StrictModel):
    """A whole household TOML file.

    The validators below are the only place cross-references between the sections are
    checked, so a bad name or a wrong-signed balance fails at load rather than seeding
    a household the engine will silently mis-project.
    """

    household: HouseholdInfo
    people: list[PersonSpec]
    accounts: list[AccountSpec]
    cash_flows: list[CashFlowSpec] = []

    @model_validator(mode="after")
    def _owners_are_known_people(self) -> HouseholdSpec:
        names = {p.name for p in self.people}
        unknown = sorted(
            {a.owner for a in self.accounts if a.owner is not None and a.owner not in names}
            | {f.owner for f in self.cash_flows if f.owner is not None and f.owner not in names}
        )
        if unknown:
            msg = f"account owner(s) not listed in [[people]]: {unknown}"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _cash_flow_targets_are_known_accounts(self) -> HouseholdSpec:
        names = {a.name for a in self.accounts}
        unknown = sorted(
            {
                f.target_account
                for f in self.cash_flows
                if f.target_account is not None and f.target_account not in names
            }
        )
        if unknown:
            msg = f"cash flow target_account(s) not listed in [[accounts]]: {unknown}"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _tax_treatments_are_known_to_the_regime(self) -> HouseholdSpec:
        try:
            regime = regime_for(self.household.tax_country)
        except KeyError as e:
            msg = f"no tax regime for country {self.household.tax_country!r}"
            raise ValueError(msg) from e
        valid = regime.valid_treatments()
        bad = sorted(
            {(a.name, a.tax_treatment) for a in self.accounts if a.tax_treatment not in valid}
        )
        if bad:
            msg = (
                f"account(s) with an unknown tax_treatment: {bad}. Valid treatments for "
                f"{self.household.tax_country}: {sorted(valid)}"
            )
            raise ValueError(msg)
        return self


def load_household_spec(path: Path) -> HouseholdSpec:
    """Parse and validate a household TOML file. Raises loudly on a missing or bad file."""
    if not path.exists():
        msg = (
            f"No household data file at {path}. Create it with:\n"
            f"    mkdir -p {path.parent} && cp household.example.toml {path}\n"
            f"then fill in your own data."
        )
        raise FileNotFoundError(msg)
    with path.open("rb") as f:
        data = tomllib.load(f)
    return HouseholdSpec.model_validate(data)


def _default_household_path() -> Path:
    env = os.environ.get("VUURTOREN_HOUSEHOLD")
    return Path(env) if env else DEFAULT_HOUSEHOLD_PATH


def seed_household(session: Session, spec: HouseholdSpec | None = None) -> int:
    """Create the household, people, accounts and baseline scenario. Returns the household id.

    If no spec is given, loads it from VUURTOREN_HOUSEHOLD or data/household.toml.
    """
    if spec is None:
        spec = load_household_spec(_default_household_path())

    household = HouseholdRow(
        name=spec.household.name,
        tax_country=spec.household.tax_country,
        fiscal_partners=spec.household.fiscal_partners,
        life_expectancy_age=spec.household.life_expectancy_age,
    )
    session.add(household)
    session.flush()

    person_rows = [
        PersonRow(
            household_id=household.id,
            name=p.name,
            birth_date=p.birth_date,
            tax_residence=p.tax_residence,
            us_person=p.us_person,
            us_filing_status=p.us_filing_status,
        )
        for p in spec.people
    ]
    session.add_all(person_rows)
    session.flush()
    person_id_by_name = {row.name: row.id for row in person_rows}

    account_rows = [
        AccountRow(
            household_id=household.id,
            owner_person_id=person_id_by_name[a.owner] if a.owner else None,
            name=a.name,
            kind=a.kind,
            tax_treatment=a.tax_treatment,
            overlay_treatment=a.overlay_treatment,
            isin=a.isin,
            price_source=a.price_source,
            currency=a.currency,
            units=a.units,
            manual_value=a.manual_value,
            cost_basis=a.cost_basis,
            return_assumption=a.return_assumption,
            distribution_yield=a.distribution_yield,
            fund_realized_gain_yield=a.fund_realized_gain_yield,
            volatility_assumption=a.volatility_assumption,
            liquid_from=a.liquid_from,
        )
        for a in spec.accounts
    ]
    session.add_all(account_rows)
    session.flush()
    account_id_by_name = {row.name: row.id for row in account_rows}

    session.add_all(
        [
            CashFlowRow(
                household_id=household.id,
                owner_person_id=person_id_by_name[f.owner] if f.owner else None,
                label=f.label,
                amount_monthly=f.amount_monthly,
                kind=f.kind,
                target_account_id=account_id_by_name[f.target_account]
                if f.target_account
                else None,
                start_date=f.start_date,
                end_date=f.end_date,
                inflation_linked=f.inflation_linked,
            )
            for f in spec.cash_flows
        ]
    )
    session.add(ScenarioRow(household_id=household.id, name="Baseline", is_baseline=True))
    session.commit()
    return household.id


def main() -> None:
    """Seed the app database from the household TOML.

        uv run python -m vuurtoren.seed

    Opens the same file the server does (VUURTOREN_DB or data/vuurtoren.db), runs the
    migrations, and seeds from VUURTOREN_HOUSEHOLD or data/household.toml. Refuses to
    run against a database that already holds a household -- edit through the app (or
    delete the .db and re-seed) instead of seeding twice.
    """
    db_path = default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(db_path)
    upgrade_to_head(engine)
    with sessionmaker(bind=engine)() as session:
        existing = session.query(HouseholdRow).first()
        if existing is not None:
            sys.exit(
                f"{db_path} already holds household {existing.id} ({existing.name!r}) "
                f"-- not seeding twice. Delete the file to start over."
            )
        household_id = seed_household(session)
    print(  # noqa: T201  # CLI entry point; stdout is the interface
        f"seeded household {household_id} into {db_path} from {_default_household_path()}"
    )


if __name__ == "__main__":
    main()
