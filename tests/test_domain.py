"""Tests for the country-neutral domain value objects (invariant 5 in CONTRIBUTING.md)."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from vuurtoren.domain import (
    Account,
    AccountKind,
    BuyProperty,
    ChangeTaxResidence,
    Household,
    Milestone,
    Person,
    ScenarioOverrides,
)


def test_a_milestone_parses_its_params_into_the_exact_type() -> None:
    """A milestone's params dict parses into the concrete BuyProperty type."""
    m = Milestone(
        id=1,
        household_id=1,
        label="Buy",
        on_date=date(2028, 6, 1),
        params={
            "type": "buy_property",
            "price": "360000",
            "mortgage": "340000",
            "annual_rate": "0.042",
        },
    )
    assert isinstance(m.params, BuyProperty)
    assert m.params.price == Decimal(360000)


def test_an_unknown_param_type_is_rejected() -> None:
    """A milestone params type outside the discriminated union is rejected."""
    with pytest.raises(ValidationError):
        Milestone(
            id=1,
            household_id=1,
            label="?",
            on_date=date(2028, 6, 1),
            params={"type": "buy_a_boat", "price": "1"},
        )


def test_a_malformed_param_payload_is_rejected() -> None:
    """A milestone params payload with an unparsable field value is rejected."""
    with pytest.raises(ValidationError):
        Milestone(
            id=1,
            household_id=1,
            label="?",
            on_date=date(2028, 6, 1),
            params={"type": "buy_property", "price": "not a number"},
        )


def test_change_of_tax_residence_is_a_milestone_type() -> None:
    """change_tax_residence parses into ChangeTaxResidence with its country field."""
    m = Milestone(
        id=1,
        household_id=1,
        label="Vienna",
        on_date=date(2029, 9, 1),
        params={"type": "change_tax_residence", "country": "AT"},
    )
    assert isinstance(m.params, ChangeTaxResidence)
    assert m.params.country == "AT"


def test_domain_objects_are_frozen() -> None:
    """A domain value object rejects attribute assignment after construction."""
    h = Household(id=1, name="T")
    with pytest.raises(ValidationError):
        h.name = "other"  # ty: ignore[invalid-assignment]


def test_household_defaults_to_the_netherlands() -> None:
    """A household with no tax_country given defaults to NL."""
    assert Household(id=1, name="T").tax_country == "NL"


def test_kind_and_tax_treatment_are_independent() -> None:
    """The same economic kind can carry different tax treatments."""
    taxed = Account(
        id=1,
        household_id=1,
        name="World equity fund",
        kind=AccountKind.EQUITY,
        tax_treatment="nl.box3_investment",
        manual_value=Decimal(50000),
    )
    sheltered = Account(
        id=2,
        household_id=1,
        name="Lijfrente",
        kind=AccountKind.PENSION,
        tax_treatment="nl.box1_pension",
        manual_value=Decimal(12000),
    )
    assert taxed.kind is not sheltered.kind
    assert taxed.tax_treatment != sheltered.tax_treatment


def test_scenario_overrides_are_country_keyed() -> None:
    """ScenarioOverrides.tax nests as country, then year, then field."""
    o = ScenarioOverrides(tax={"NL": {2028: {"box3_rate": Decimal("0.40")}}})
    assert o.tax["NL"][2028]["box3_rate"] == Decimal("0.40")


def test_empty_overrides_are_the_default() -> None:
    """A ScenarioOverrides built with no arguments has empty tax and assumptions."""
    o = ScenarioOverrides()
    assert o.tax == {}
    assert o.assumptions == {}


def test_a_person_is_not_a_us_person_by_default() -> None:
    """Citizenship taxation is opt-in; the overwhelming majority of households never see it."""
    person = Person(id=1, household_id=1, name="A")

    assert person.us_person is False
    assert person.us_filing_status is None


def test_a_us_filing_status_accepts_the_three_modelled_values() -> None:
    """Three values, because only three change the arithmetic."""
    for status in ("single", "married_filing_separately", "married_filing_jointly"):
        person = Person(id=1, household_id=1, name="A", us_person=True, us_filing_status=status)

        assert person.us_filing_status == status


def test_an_unknown_filing_status_is_rejected() -> None:
    """Head of household is deliberately absent: it needs a dependent the domain lacks."""
    with pytest.raises(ValidationError):
        Person(id=1, household_id=1, name="A", us_filing_status="head_of_household")  # ty: ignore[invalid-argument-type]


def test_an_account_has_no_overlay_treatment_by_default() -> None:
    """The third classification is absent unless a citizenship overlay applies."""
    account = Account(
        id=1,
        household_id=1,
        name="Brokerage",
        kind=AccountKind.EQUITY,
        tax_treatment="nl.box3_investment",
    )

    assert account.overlay_treatment is None


def test_an_account_carries_residence_and_overlay_treatments_independently() -> None:
    """A retained US brokerage account is in Box 3 and in the US net at the same time.

    The two keys are orthogonal on purpose: the US overlay must never read an `nl.*` key
    and NL must never read a `us.*` one.
    """
    account = Account(
        id=1,
        household_id=1,
        name="Schwab",
        kind=AccountKind.EQUITY,
        tax_treatment="nl.box3_investment",
        overlay_treatment="us.non_pfic",
    )

    assert account.tax_treatment == "nl.box3_investment"
    assert account.overlay_treatment == "us.non_pfic"
