"""Storage. Every top-level row carries household_id.

Each row maps to a domain value object via to_domain(). Nothing else crosses that
boundary — the engine imports `domain`, never this module.
"""

from datetime import date  # noqa: TC003  # SQLAlchemy resolves Mapped[] annotations at runtime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from vuurtoren import domain
from vuurtoren.db import Base, ExactDecimal, Money

if TYPE_CHECKING:
    from pydantic import BaseModel


def _from_columns[D: BaseModel](row: Base, model: type[D], **override: object) -> D:
    """Validate `model` from every mapped column of `row`.

    Built from the columns, not a hand-written list, so a new column reaches the domain
    object without a second edit.
    """
    return model.model_validate(
        {c.name: getattr(row, c.name) for c in row.__table__.columns} | override
    )


class HouseholdRow(Base):
    """The household every other table's rows hang off."""

    __tablename__ = "household"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, default="Household")
    base_currency: Mapped[str] = mapped_column(String, default="EUR")
    tax_country: Mapped[str] = mapped_column(String, default="NL")
    fiscal_partners: Mapped[bool] = mapped_column(default=False)
    life_expectancy_age: Mapped[int] = mapped_column(default=95)

    def to_domain(self) -> domain.Household:
        """The frozen `domain.Household` this row maps to."""
        return _from_columns(self, domain.Household)


class PersonRow(Base):
    """A member of the household."""

    __tablename__ = "person"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("household.id"))
    name: Mapped[str]
    birth_date: Mapped[date]
    tax_residence: Mapped[str] = mapped_column(String, default="NL")
    pension_age_override: Mapped[str | None] = mapped_column(default=None)
    us_person: Mapped[bool] = mapped_column(default=False)
    us_filing_status: Mapped[str | None] = mapped_column(String, default=None)

    def to_domain(self) -> domain.Person:
        """The frozen `domain.Person` this row maps to."""
        return _from_columns(self, domain.Person)


class AccountRow(Base):
    """One asset or debt position. Money columns are `Money`/`ExactDecimal`, never float."""

    __tablename__ = "account"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("household.id"))
    owner_person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id"), default=None)
    name: Mapped[str] = mapped_column(default="")
    kind: Mapped[domain.AccountKind] = mapped_column(default=domain.AccountKind.CASH)
    tax_treatment: Mapped[str] = mapped_column(String, default="")
    overlay_treatment: Mapped[str | None] = mapped_column(String, default=None)
    isin: Mapped[str | None] = mapped_column(default=None)
    price_source: Mapped[domain.PriceSource] = mapped_column(default=domain.PriceSource.MANUAL)
    currency: Mapped[str] = mapped_column(String, default="EUR")
    units: Mapped[Decimal | None] = mapped_column(ExactDecimal, default=None)
    manual_value: Mapped[Decimal | None] = mapped_column(Money, default=None)
    cost_basis: Mapped[Decimal | None] = mapped_column(Money, default=None)
    return_assumption: Mapped[float] = mapped_column(default=0.0)
    volatility_assumption: Mapped[float] = mapped_column(default=0.0)
    expense_ratio: Mapped[float] = mapped_column(default=0.0)
    distribution_yield: Mapped[float] = mapped_column(default=0.0)
    fund_realized_gain_yield: Mapped[float] = mapped_column(default=0.0)
    liquid_from: Mapped[date | None] = mapped_column(default=None)

    def to_domain(self) -> domain.Account:
        """The frozen `domain.Account` this row maps to."""
        return _from_columns(self, domain.Account)


class PricePointRow(Base):
    """One dated price for an account, in its native currency and converted to EUR.

    Has no `to_domain`: the engine never sees a price point. The API opens each account
    on its latest `value_eur` instead of `manual_value` (`api/deps.py`).
    """

    __tablename__ = "price_point"
    __table_args__ = (UniqueConstraint("account_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"))
    date: Mapped[date]
    price_native: Mapped[Decimal] = mapped_column(ExactDecimal)
    currency: Mapped[str]
    fx_rate_to_eur: Mapped[Decimal] = mapped_column(ExactDecimal)
    value_eur: Mapped[Decimal] = mapped_column(Money)
    source: Mapped[str]


class CashFlowRow(Base):
    """A recurring monthly income, expense or contribution."""

    __tablename__ = "cash_flow"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("household.id"))
    owner_person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id"), default=None)
    label: Mapped[str] = mapped_column(default="")
    amount_monthly: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    kind: Mapped[domain.CashFlowKind] = mapped_column(default=domain.CashFlowKind.EXPENSE)
    target_account_id: Mapped[int | None] = mapped_column(ForeignKey("account.id"), default=None)
    start_date: Mapped[date | None] = mapped_column(default=None)
    end_date: Mapped[date | None] = mapped_column(default=None)
    inflation_linked: Mapped[bool] = mapped_column(default=True)

    def to_domain(self) -> domain.CashFlow:
        """The frozen `domain.CashFlow` this row maps to."""
        return _from_columns(self, domain.CashFlow)


class MilestoneRow(Base):
    """A one-off plan event. `params` is the JSON blob `domain.MilestoneParams` discriminates."""

    __tablename__ = "milestone"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("household.id"))
    label: Mapped[str] = mapped_column(default="")
    on_date: Mapped[date | None] = mapped_column(default=None)
    age_person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id"), default=None)
    age_years: Mapped[int | None] = mapped_column(default=None)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    def to_domain(self) -> domain.Milestone:
        """The frozen `domain.Milestone` this row maps to, with `params` validated."""
        return _from_columns(self, domain.Milestone)


class ScenarioRow(Base):
    """A named what-if. `overrides` is the JSON blob `domain.ScenarioOverrides` validates."""

    __tablename__ = "scenario"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("household.id"))
    name: Mapped[str] = mapped_column(default="")
    is_baseline: Mapped[bool] = mapped_column(default=False)
    overrides: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    def to_domain(self) -> domain.Scenario:
        """The frozen `domain.Scenario` this row maps to, with `overrides` validated."""
        return _from_columns(self, domain.Scenario, overrides=self.overrides or {})
