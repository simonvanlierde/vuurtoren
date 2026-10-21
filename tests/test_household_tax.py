"""`HouseholdTax` — the composite that lets a second regime be consulted per person."""

from dataclasses import replace
from decimal import Decimal

import numpy as np
import pytest

from vuurtoren.domain import Person
from vuurtoren.tax.config import defaults_for
from vuurtoren.tax.household import HouseholdTax
from vuurtoren.tax.nl.config import NLTaxConfig
from vuurtoren.tax.nl.regime import NLTaxRegime
from vuurtoren.tax.overlay import PersonSlice, TreatmentMaps
from vuurtoren.tax.regime import YearState
from vuurtoren.tax.us.config import USTaxConfig

CFG = defaults_for("NL", 2026, expect=NLTaxConfig)


def _year_state() -> YearState:
    """A household with one Box 3 investor and a joint bank account."""
    one = np.ones(1)
    return YearState(
        year=2026,
        balances_by_treatment={
            "nl.box3_investment": one * 400_000.0,
            "nl.box3_bank": one * 20_000.0,
        },
        home_value=np.zeros(1),
        mortgage_interest_paid=np.zeros(1),
        fiscal_partners=False,
        by_person={
            1: PersonSlice(
                person_id=1,
                owned=TreatmentMaps(balances={"nl.box3_investment": one * 400_000.0}),
                joint=TreatmentMaps(balances={"nl.box3_bank": one * 20_000.0}),
                earned_income=np.zeros(1),
            )
        },
    )


def _a_us_person() -> Person:
    return Person(id=1, household_id=1, name="A", us_person=True, us_filing_status="single")


class _Spy:
    """Records the credit input it is handed and charges nothing."""

    citizenship = "NL"  # a country whose config resolves; the overlay's own maths is stubbed

    def __init__(self) -> None:
        self.seen: list[np.ndarray] = []

    def annual_tax(self, s, cfg, *, residence_tax, carry):  # noqa: ANN001, ANN202
        self.seen.append(np.asarray(residence_tax).copy())
        return np.zeros_like(residence_tax), carry

    def withdrawal_tax(self, amount, *, treatment, realized_gain, cfg):  # noqa: ANN001, ANN202
        return np.full_like(np.asarray(amount, dtype=float), 100.0)

    def valid_treatments(self):  # noqa: ANN202
        return frozenset()

    def validate_accounts(self, accounts, *, person):  # noqa: ANN001, ANN202
        return None


class _FlatCharge(_Spy):
    """Charges a flat 100 per run on top of the residence tax."""

    def annual_tax(self, s, cfg, *, residence_tax, carry):  # noqa: ANN001, ANN202
        return np.full_like(np.asarray(residence_tax, dtype=float), 100.0), carry


def test_with_no_overlays_it_is_the_residence_regime() -> None:
    """The no-US-person case must be indistinguishable from not having a composite."""
    residence = NLTaxRegime()
    wrapped = HouseholdTax(residence=residence)
    state = _year_state()

    assert wrapped.country == residence.country
    assert wrapped.valid_treatments() == residence.valid_treatments()
    assert wrapped.sweep_excluded_treatments() == residence.sweep_excluded_treatments()
    assert wrapped.actual_return_treatments() == residence.actual_return_treatments()
    assert wrapped.annual_investment_tax(state, CFG) == pytest.approx(
        residence.annual_investment_tax(state, CFG)
    )


def test_the_overlay_is_handed_the_residence_tax_as_its_credit_input() -> None:
    """The ordering rule: residence tax first, then the overlay measured against it."""
    residence = NLTaxRegime()
    spy = _Spy()
    state = _year_state()
    wrapped = HouseholdTax(residence=residence, overlays=((_a_us_person(), spy),))

    wrapped.annual_investment_tax(state, CFG)

    assert spy.seen, "the overlay was never consulted"
    # The only person holds the whole taxed base, so their share of the residence tax is
    # all of it.
    assert spy.seen[0] == pytest.approx(residence.annual_investment_tax(state, CFG))


def test_the_household_total_is_residence_plus_overlay() -> None:
    """An overlay adds to the residence charge; it never replaces it."""
    residence = NLTaxRegime()
    state = _year_state()
    wrapped = HouseholdTax(residence=residence, overlays=((_a_us_person(), _FlatCharge()),))

    assert wrapped.annual_investment_tax(state, CFG) == pytest.approx(
        residence.annual_investment_tax(state, CFG) + 100.0
    )


def test_an_overlay_for_someone_absent_from_the_year_is_skipped() -> None:
    """A person with no slice — joined the household mid-projection — must not crash."""
    residence = NLTaxRegime()
    stranger = Person(id=99, household_id=1, name="Z", us_person=True)
    wrapped = HouseholdTax(residence=residence, overlays=((stranger, _FlatCharge()),))
    state = _year_state()

    assert wrapped.annual_investment_tax(state, CFG) == pytest.approx(
        residence.annual_investment_tax(state, CFG)
    )


def test_a_withdrawal_is_charged_by_the_owners_overlay() -> None:
    """The gap phase 2 pinned, now closed: the overlay gets figures for the sale's year.

    A US person selling a retained brokerage holding owes US capital gains tax on top of
    whatever the Netherlands charges, so the composite has to reach the overlay here.
    """
    residence = NLTaxRegime()
    wrapped = HouseholdTax(residence=residence, overlays=((_a_us_person(), _FlatCharge()),))
    amount = np.array([10_000.0])
    kwargs = {
        "treatment": "nl.box3_investment",
        "realized_gain": np.array([4_000.0]),
        "owner_person_id": 1,
        "year": 2026,
        "cfg": CFG,
    }

    charged = wrapped.withdrawal_tax(amount, **kwargs)

    assert charged == pytest.approx(residence.withdrawal_tax(amount, **kwargs) + 100.0)


def test_a_joint_accounts_sale_reaches_no_overlay() -> None:
    """Attributing a sale out of a joint account to one citizen needs a rule we do not have.

    The filing-status share is an annual-tax concept applied to balances; applying it to a
    realization would be a different rule on a different base. Left to the overlay's annual
    charge rather than guessed at, and pinned so the omission is visible.
    """
    residence = NLTaxRegime()
    wrapped = HouseholdTax(residence=residence, overlays=((_a_us_person(), _FlatCharge()),))
    amount = np.array([10_000.0])
    kwargs = {
        "treatment": "nl.box3_investment",
        "realized_gain": np.array([4_000.0]),
        "owner_person_id": None,
        "year": 2026,
        "cfg": CFG,
    }

    assert wrapped.withdrawal_tax(amount, **kwargs) == pytest.approx(
        residence.withdrawal_tax(amount, **kwargs)
    )


class _CfgSpy(_Spy):
    """Records the overlay config it is handed."""

    citizenship = "US"

    def __init__(self) -> None:
        super().__init__()
        self.cfgs: list[object] = []

    def annual_tax(self, s, cfg, *, residence_tax, carry):  # noqa: ANN001, ANN202
        self.cfgs.append(cfg)
        return np.zeros_like(residence_tax), carry


def test_the_overlay_config_is_indexed_like_the_residence_one() -> None:
    """A 2050 overlay config is in 2050 money: indexed allowances, fixed thresholds kept.

    The overlay's config was resolved bare, so a 2050 bracket stayed in source-year
    dollars while the income it taxed had inflated for decades.
    """
    spy = _CfgSpy()
    # 2050 is under the actual-return regime, which needs a gain to tax.
    state = replace(_year_state(), year=2050, investment_gain=np.zeros(1))
    wrapped = HouseholdTax(
        residence=NLTaxRegime(), overlays=((_a_us_person(), spy),), index_inflation=0.02
    )
    wrapped.annual_investment_tax(state, CFG)

    base = defaults_for("US", 2050, expect=USTaxConfig)
    (seen,) = spy.cfgs
    assert isinstance(seen, USTaxConfig)
    factor = Decimal(str(1.02 ** (2050 - base.source_year)))
    assert seen.standard_deduction_single == pytest.approx(base.standard_deduction_single * factor)
    # NIIT thresholds are fixed by statute and never indexed.
    assert seen.niit_threshold_single == base.niit_threshold_single


class _YearCounter(_Spy):
    """Carries a count of the years it has charged, and records the carry it is handed."""

    def __init__(self) -> None:
        super().__init__()
        self.carries_in: list[object] = []

    def annual_tax(self, s, cfg, *, residence_tax, carry):  # noqa: ANN001, ANN202
        self.carries_in.append(carry)
        return np.zeros_like(residence_tax), (carry or 0) + 1


def test_close_year_threads_each_overlays_carry_and_asking_advances_nothing() -> None:
    """The successor carries the year forward; `annual_investment_tax` leaves it alone."""
    counter = _YearCounter()
    state = _year_state()
    wrapped = HouseholdTax(residence=NLTaxRegime(), overlays=((_a_us_person(), counter),))

    wrapped.annual_investment_tax(state, CFG)
    _, after_one = wrapped.close_year(state, CFG)
    after_one.annual_investment_tax(state, CFG)
    _, after_two = after_one.close_year(state, CFG)

    assert counter.carries_in == [None, None, 1, 1]
    assert wrapped.carries == ()
    assert after_two.carries == (2,)
