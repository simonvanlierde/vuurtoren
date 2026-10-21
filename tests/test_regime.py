"""NLTaxRegime: the TaxRegime protocol implementation for the Dutch tax figures."""

from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from vuurtoren.tax.nl.config import NLTaxConfig, defaults_for
from vuurtoren.tax.nl.regime import NLTaxRegime
from vuurtoren.tax.regime import TaxRegime, YearState, regime_for

CFG = defaults_for("NL", 2026, expect=NLTaxConfig)


def state(**kw: object) -> YearState:
    """Build a YearState with sensible defaults, overridden by the given keyword arguments."""
    base = {
        "year": 2026,
        "balances_by_treatment": {},
        "investment_gain": None,
        "home_value": np.zeros(1),
        "mortgage_interest_paid": np.zeros(1),
        "fiscal_partners": False,
    }
    return YearState(**(base | kw))  # ty: ignore[invalid-argument-type]


def test_nl_regime_satisfies_the_protocol() -> None:
    """NLTaxRegime implements the five-method TaxRegime protocol the engine relies on."""
    assert isinstance(NLTaxRegime(), TaxRegime)


def test_regime_for_returns_the_dutch_regime() -> None:
    """The regime registry resolves "NL" to the Dutch regime."""
    assert regime_for("NL").country == "NL"


def test_an_unknown_country_fails_loudly() -> None:
    """An unregistered country code fails loudly rather than silently defaulting."""
    with pytest.raises(KeyError, match="XX"):
        regime_for("XX")


def test_wealth_tax_reads_only_box3_treatments() -> None:
    """The wealth tax base includes only Box 3 treatments, excluding Box 1 pension balances."""
    r = NLTaxRegime()
    s = state(
        balances_by_treatment={
            "nl.box3_investment": np.array([100_000.0]),
            "nl.box1_pension": np.array([500_000.0]),  # must be excluded from the wealth base
        }
    )
    assert r.annual_investment_tax(s, CFG)[0] == pytest.approx(877.89, abs=0.005)


def test_wealth_tax_splits_bank_from_investments() -> None:
    """Bank and investment balances use different forfait rates, so equal wealth taxes differ."""
    r = NLTaxRegime()
    banky = state(balances_by_treatment={"nl.box3_bank": np.array([150_000.0])})
    equity = state(balances_by_treatment={"nl.box3_investment": np.array([150_000.0])})
    assert r.annual_investment_tax(banky, CFG)[0] < r.annual_investment_tax(equity, CFG)[0]


def test_wealth_tax_deducts_box3_debt() -> None:
    """A stored Box 3 DEBT balance reduces the taxable wealth base."""
    r = NLTaxRegime()
    plain = state(balances_by_treatment={"nl.box3_investment": np.array([200_000.0])})
    indebted = state(
        balances_by_treatment={
            "nl.box3_investment": np.array([200_000.0]),
            "nl.box3_debt": np.array([-50_000.0]),  # DEBT balances are stored negative
        }
    )
    assert r.annual_investment_tax(indebted, CFG)[0] < r.annual_investment_tax(plain, CFG)[0]


def test_wealth_tax_rejects_a_wrong_sign_positive_debt() -> None:
    """A positive DEBT balance is a sign bug and must fail loudly, not zero the deduction."""
    # DEBT balances are stored negative; a positive one is a sign bug that must fail
    # loudly rather than silently zero the Box 3 deduction.
    r = NLTaxRegime()
    s = state(balances_by_treatment={"nl.box3_debt": np.array([50_000.0])})
    with pytest.raises(ValueError, match="debt must not be negative"):
        r.annual_investment_tax(s, CFG)


def test_wealth_tax_switches_regime_in_2028() -> None:
    """From 2028, the regime's wealth tax uses the actual-return (WWR) calculation."""
    r = NLTaxRegime()
    s = state(
        year=2028,
        balances_by_treatment={"nl.box3_investment": np.array([100_000.0])},
        investment_gain=np.array([11_800.0]),
    )
    assert r.annual_investment_tax(s, CFG)[0] == pytest.approx(3600.00, abs=0.005)


def test_wealth_tax_in_2028_requires_an_actual_return() -> None:
    """In the WWR regime, a missing actual return fails loudly instead of assuming zero."""
    r = NLTaxRegime()
    s = state(
        year=2028,
        balances_by_treatment={"nl.box3_investment": np.array([100_000.0])},
        investment_gain=None,
    )
    with pytest.raises(ValueError, match="actual_return"):
        r.annual_investment_tax(s, CFG)


def test_wealth_tax_elects_the_tegenbewijs_when_the_actual_return_is_lower() -> None:
    """The regime elects the tegenbewijs when the provided actual return is below the forfait."""
    r = NLTaxRegime()
    s = state(
        balances_by_treatment={"nl.box3_investment": np.array([100_000.0])},
        investment_gain=np.array([1000.0]),
    )
    assert r.annual_investment_tax(s, CFG)[0] == pytest.approx(360.00, abs=0.005)


def test_wealth_tax_elects_a_proven_zero_actual_return() -> None:
    """A proven-zero actual return (not None) elects the tegenbewijs and zeroes the wealth tax."""
    r = NLTaxRegime()
    s = state(
        balances_by_treatment={"nl.box3_investment": np.array([100_000.0])},
        investment_gain=np.zeros(1),
    )
    assert r.annual_investment_tax(s, CFG)[0] == 0.0


def test_housing_adjustment_is_positive_when_interest_exceeds_the_forfait() -> None:
    """The housing adjustment is a positive HRA benefit once interest exceeds the forfait."""
    r = NLTaxRegime()
    s = state(home_value=np.array([400_000.0]), mortgage_interest_paid=np.array([14_000.0]))
    assert r.annual_housing_adjustment(s, CFG)[0] == pytest.approx(4732.56, abs=0.005)


def test_housing_adjustment_is_zero_without_a_home() -> None:
    """With no home value at all, the housing adjustment is zero."""
    r = NLTaxRegime()
    assert r.annual_housing_adjustment(state(), CFG)[0] == 0.0


def test_housing_adjustment_is_negative_for_a_mortgage_free_owner() -> None:
    """The eigenwoningforfait is real imputed income once mortgage-free, net of Hillen relief."""
    # Proves the protocol's "May be negative" contract now holds: the eigenwoningforfait
    # is real imputed income once the mortgage is paid off, even net of Wet Hillen relief.
    r = NLTaxRegime()
    s = state(home_value=np.array([400_000.0]), mortgage_interest_paid=np.zeros(1))
    assert r.annual_housing_adjustment(s, CFG)[0] < 0.0


def test_purchase_costs_apply_the_starter_exemption() -> None:
    """A qualifying buy zeroes the duty and consumes the exemption; an over-age buy pays 2%."""
    r = NLTaxRegime()
    # A qualifying buy zeroes the duty and reports the exemption as consumed; a non-
    # qualifying buy (over-age) pays 2% and leaves the exemption available.
    assert r.purchase_costs(
        Decimal(360000),
        buyer_age=29,
        starter_exemption_used=False,
        mortgage_amount=Decimal(0),
        cfg=CFG,
    ) == (Decimal("0.00"), True)
    assert r.purchase_costs(
        Decimal(360000),
        buyer_age=36,
        starter_exemption_used=False,
        mortgage_amount=Decimal(0),
        cfg=CFG,
    ) == (Decimal("7200.00"), False)


def test_purchase_costs_ignores_the_exemption_once_already_used() -> None:
    """A buyer who already used the starter exemption pays the standard 2% own-occupancy rate."""
    r = NLTaxRegime()
    assert r.purchase_costs(
        Decimal(360000),
        buyer_age=29,
        starter_exemption_used=True,
        mortgage_amount=Decimal(0),
        cfg=CFG,
    ) == (Decimal("7200.00"), False)


def test_purchase_costs_charges_the_general_rate_when_not_own_occupancy() -> None:
    """A buy-to-let pays the 8% general rate, not the 2% own-home rate, never the exemption."""
    # A buy-to-let / second property pays the 8% general rate, not the 2% own-home rate,
    # regardless of the starter exemption, and never consumes it.
    r = NLTaxRegime()
    assert r.purchase_costs(
        Decimal(500000),
        buyer_age=40,
        own_occupancy=False,
        starter_exemption_used=True,
        mortgage_amount=Decimal(400000),
        cfg=CFG,
    ) == (Decimal("40000.00"), False)


def test_state_pension_date_matches_the_aow_schedule() -> None:
    """The regime's state pension date delegates to the AOW schedule."""
    r = NLTaxRegime()
    assert r.state_pension_date(date(1990, 1, 1), growth=0) == date(2057, 4, 1)


def test_valid_treatments_covers_the_seeded_accounts() -> None:
    """The regime's valid treatments include every NL account kind and no other country's."""
    treatments = NLTaxRegime().valid_treatments()
    assert "nl.box3_investment" in treatments
    assert "nl.box1_pension" in treatments
    assert "nl.box1_home" in treatments
    assert "at.kest" not in treatments


def test_every_treatment_key_is_country_prefixed() -> None:
    """Every tax_treatment key the regime recognises is prefixed with its own country code."""
    assert all(t.startswith("nl.") for t in NLTaxRegime().valid_treatments())


def test_the_actual_return_base_is_the_investment_treatment_only() -> None:
    """The tegenbewijs/WWR actual-return base is investments only; bank accounts are excluded."""
    # BANK is deliberately absent: the engine cannot yet separate a cash account's
    # interest from ordinary household flows, so tegenbewijs/WWR see investment
    # gains only. A known limitation.
    assert NLTaxRegime().actual_return_treatments() == frozenset({"nl.box3_investment"})


def test_an_overdrawn_bank_account_is_a_box_3_debt_not_a_zero() -> None:
    """An overdrawn bank balance reduces the wealth-tax base as Box 3 debt, not a clamped zero."""
    r = NLTaxRegime()
    solvent = state(
        year=2026,
        balances_by_treatment={
            "nl.box3_bank": np.zeros(1),
            "nl.box3_investment": np.array([500_000.0]),
        },
    )
    overdrawn = state(
        year=2026,
        balances_by_treatment={
            "nl.box3_bank": np.array([-200_000.0]),
            "nl.box3_investment": np.array([500_000.0]),
        },
    )
    assert r.annual_investment_tax(overdrawn, CFG)[0] < r.annual_investment_tax(solvent, CFG)[0]


def test_the_wealth_tax_takes_and_returns_run_arrays() -> None:
    """The seam works in (n_runs,) float64 arrays, one call for all runs."""
    r = NLTaxRegime()
    s = state(
        balances_by_treatment={"nl.box3_investment": np.array([100_000.0, 0.0, 500_000.0])},
        home_value=np.zeros(3),
        mortgage_interest_paid=np.zeros(3),
    )
    out = r.annual_investment_tax(s, CFG)
    assert isinstance(out, np.ndarray)
    assert out.shape == (3,)
    assert out[0] == pytest.approx(877.89, abs=0.005)  # the hand-computed 2026 example
    assert out[1] == 0.0
    assert out[2] > out[0]


def test_the_housing_adjustment_takes_and_returns_run_arrays() -> None:
    """The housing adjustment seam works in (n_runs,) float64 arrays, one call for all runs."""
    r = NLTaxRegime()
    s = state(
        home_value=np.array([400_000.0, 0.0]),
        mortgage_interest_paid=np.array([14_000.0, 0.0]),
    )
    out = r.annual_housing_adjustment(s, CFG)
    assert isinstance(out, np.ndarray)
    assert out.shape == (2,)
    assert out[0] == pytest.approx(4732.56, abs=0.005)
    assert out[1] == 0.0


def test_the_withdrawal_tax_takes_and_returns_run_arrays() -> None:
    """The withdrawal tax seam works in (n_runs,) float64 arrays, one call for all runs."""
    r = NLTaxRegime()
    out = r.withdrawal_tax(
        np.array([10_000.0, 0.0, -50.0]),
        treatment="nl.box1_pension",
        # A uitkering is taxed on the gross, so the gain is ignored — pass a wrong one
        # on purpose to prove it does not reach the answer.
        realized_gain=np.array([9_999.0, 1.0, 1.0]),
        owner_person_id=None,
        year=2026,
        cfg=CFG,
    )
    assert isinstance(out, np.ndarray)
    assert out.shape == (3,)
    assert out[0] == pytest.approx(3756.00, abs=0.005)
    assert out[1] == 0.0
    assert out[2] == 0.0  # a negative amount is a deposit, never taxed


def test_an_overdraft_stacks_with_an_existing_debt_balance() -> None:
    """The overdraft adds to a stored DEBT balance rather than replacing it."""
    r = NLTaxRegime()
    both = state(
        year=2026,
        balances_by_treatment={
            "nl.box3_bank": np.array([-100_000.0]),
            "nl.box3_debt": np.array([-100_000.0]),
            "nl.box3_investment": np.array([500_000.0]),
        },
    )
    debt_only = state(
        year=2026,
        balances_by_treatment={
            "nl.box3_bank": np.zeros(1),
            "nl.box3_debt": np.array([-100_000.0]),
            "nl.box3_investment": np.array([500_000.0]),
        },
    )
    assert r.annual_investment_tax(both, CFG)[0] < r.annual_investment_tax(debt_only, CFG)[0]
