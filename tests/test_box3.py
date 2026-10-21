"""Box 3 wealth tax: forfaitair, tegenbewijs, werkelijk rendement, and the year dispatcher."""

from dataclasses import replace
from decimal import Decimal  # noqa: TC003  # hypothesis reads the annotations at runtime

import numpy as np
import pytest
from hypothesis import given, strategies as st

from vuurtoren.tax.household import HouseholdTax
from vuurtoren.tax.nl.box3 import box3_tax_array, forfaitair_income_array
from vuurtoren.tax.nl.config import NLTaxConfig, defaults_for
from vuurtoren.tax.nl.regime import BANK, DEBT, INVESTMENT, NLTaxRegime
from vuurtoren.tax.overlay import TreatmentMaps
from vuurtoren.tax.regime import YearState

CFG = defaults_for("NL", 2026, expect=NLTaxConfig)
EUR = 0.01


def _a(x: float | Decimal) -> np.ndarray:
    return np.array([float(x)])


def tax(
    bank: float | Decimal = 0,
    investments: float | Decimal = 0,
    debt: float | Decimal = 0,
    actual: float | Decimal | None = None,
    *,
    partners: bool = False,
    year: int = 2026,
    cfg: NLTaxConfig = CFG,
    elect: bool = True,
) -> float:
    """The engine's Box 3 tax for one run, in euros."""
    got = box3_tax_array(
        _a(bank),
        _a(investments),
        _a(debt),
        None if actual is None else _a(actual),
        year=year,
        fiscal_partners=partners,
        cfg=cfg,
        elect=elect,
    )
    return float(got[0])


def test_below_the_allowance_there_is_no_tax() -> None:
    """Wealth below the heffingsvrij vermogen allowance is untaxed."""
    assert tax(bank=50000) == 0


def test_exactly_at_the_allowance_there_is_no_tax() -> None:
    """Wealth exactly at the allowance is still untaxed (inclusive boundary)."""
    assert tax(bank=59357) == 0


def test_hand_computed_single_filer_all_investments() -> None:
    """A single filer's forfaitair tax on all-investment wealth matches the hand-computed figure."""
    # grondslag 100000; hvv 59357; aandeel = 40643/100000 = 0.40643
    # rendement = 100000 * 0.06 = 6000; voordeel = 6000 * 0.40643 = 2438.58
    # tax = 2438.58 * 0.36 = 877.8888 -> 877.89
    assert tax(investments=100000) == 877.89


def test_hand_computed_mixed_bank_and_investments() -> None:
    """A mixed bank/investment wealth base is taxed using each asset class's own forfait rate."""
    # grondslag 150000; hvv 59357; aandeel = 90643/150000
    # rendement = 50000*0.0128 + 100000*0.06 = 640 + 6000 = 6640
    # voordeel = 6640 * 0.6042866... = 4012.4613...; tax = *0.36 = 1444.486...
    assert tax(bank=50000, investments=100000) == 1444.49


def test_debt_below_the_threshold_is_ignored() -> None:
    """Debt below the drempel is not deducted from the Box 3 wealth base."""
    assert tax(investments=100000, debt=3000) == tax(investments=100000)


def test_debt_above_the_threshold_reduces_tax() -> None:
    """Debt above the drempel reduces the taxable Box 3 wealth base."""
    assert tax(investments=100000, debt=20000) < tax(investments=100000)


def test_fiscal_partners_double_the_allowance() -> None:
    """Fiscal partners get double the heffingsvrij vermogen allowance of a single filer."""
    assert tax(investments=118714, partners=True) == 0


def test_fiscal_partners_pay_less_than_a_single_filer() -> None:
    """On identical wealth, fiscal partners owe less Box 3 tax than a single filer."""
    assert tax(investments=200000, partners=True) < tax(investments=200000)


def test_moving_capital_into_a_house_removes_it_from_the_base() -> None:
    """A primary residence is Box 1, so buying one lowers Box 3 tax."""
    assert tax(bank=20000) < tax(bank=300000)
    assert tax(bank=20000) == 0


def test_negative_net_wealth_is_not_taxed() -> None:
    """Net wealth (assets minus debt) below zero is untaxed, not a negative tax."""
    assert tax(bank=10000, debt=50000) == 0


def test_forfaitair_income_is_exposed_for_the_tegenbewijs_comparison() -> None:
    """The forfaitair income figure, not just the tax, is available for the tegenbewijs check."""
    got = forfaitair_income_array(_a(0), _a(100000), _a(0), fiscal_partners=False, cfg=CFG)
    assert got[0] == 2438.58


amounts = st.decimals(min_value=0, max_value=5_000_000, places=2)


@given(wealth=amounts)
def test_property_tax_is_never_negative(wealth: Decimal) -> None:
    """The forfaitair tax is never negative for any non-negative investment wealth."""
    assert tax(investments=wealth) >= 0


@given(a=amounts, b=amounts)
def test_property_tax_is_monotonic_in_wealth(a: Decimal, b: Decimal) -> None:
    """More investment wealth never produces less forfaitair tax."""
    lo, hi = sorted((a, b))
    assert tax(investments=lo) <= tax(investments=hi)


@given(wealth=amounts)
def test_property_partners_never_pay_more_than_singles(wealth: Decimal) -> None:
    """On identical wealth, fiscal partners never owe more forfaitair tax than a single filer."""
    assert tax(investments=wealth, partners=True) <= tax(investments=wealth)


@given(wealth=amounts)
def test_property_tax_never_exceeds_the_forfaitair_return(wealth: Decimal) -> None:
    """The forfaitair tax never exceeds 36% of the assumed forfaitair return on the wealth."""
    cap = float(wealth * CFG.box3_forfait_investments * CFG.box3_rate)
    assert tax(investments=wealth) <= cap + EUR


def test_negative_inputs_are_rejected() -> None:
    """A negative bank balance is rejected as invalid."""
    with pytest.raises(ValueError, match="bank must not be negative"):
        tax(bank=-1)


def test_tegenbewijs_applies_when_the_actual_return_is_lower() -> None:
    """The tegenbewijs is elected when a proven actual return is lower than the forfait."""
    # forfaitair income is 2438.58, so the actual return of 1000 wins: 1000 * 0.36
    assert tax(investments=100000, actual=1000) == 360.00


def test_tegenbewijs_is_ignored_when_the_actual_return_is_higher() -> None:
    """The tegenbewijs is not elected when the actual return exceeds the forfait."""
    assert tax(investments=100000, actual=9000) == 877.89


def test_a_loss_year_produces_no_tax() -> None:
    """A proven negative actual return produces zero Box 3 tax via the tegenbewijs."""
    assert tax(investments=100000, actual=-20000) == 0


def test_forcing_the_forfaitair_path_ignores_the_actual_return() -> None:
    """With elect=False, the forfaitair tax applies even when a lower actual return is known."""
    assert tax(investments=100000, actual=1000, elect=False) == 877.89


def test_no_actual_return_supplied_falls_back_to_forfaitair() -> None:
    """With no actual return supplied, the tegenbewijs path falls back to the forfaitair tax."""
    assert tax(investments=100000) == 877.89


@given(wealth=amounts, actual=st.decimals(min_value=-100_000, max_value=500_000, places=2))
def test_property_tegenbewijs_never_costs_more_than_forfaitair(
    wealth: Decimal, actual: Decimal
) -> None:
    """Electing the tegenbewijs never produces more tax than staying on the forfaitair path."""
    assert tax(investments=wealth, actual=actual) <= tax(investments=wealth)


def test_wwr_taxes_actual_return_above_the_allowance() -> None:
    """Regime B taxes only the actual return above the WWR allowance, at the WWR rate."""
    # actual return 11800, minus the 1800 allowance, taxed at 36%
    assert tax(investments=200000, actual=11800, year=2028) == 3600.00


def test_wwr_allowance_doubles_for_fiscal_partners() -> None:
    """The WWR allowance doubles for fiscal partners, same as the forfaitair allowance."""
    assert tax(investments=200000, actual=3600, year=2028, partners=True) == 0
    assert tax(investments=200000, actual=3600, year=2028) == 648.00


def test_wwr_ignores_wealth_and_taxes_only_return() -> None:
    """Regime B taxes only the actual return, not the size of the underlying wealth."""
    small = tax(investments=10000, actual=11800, year=2028)
    assert small == tax(investments=5000000, actual=11800, year=2028)


def test_wwr_loss_year_is_untaxed() -> None:
    """A negative actual return under regime B produces zero tax rather than a rebate."""
    assert tax(investments=200000, actual=-30000, year=2028) == 0


def test_dispatcher_uses_regime_a_before_the_switch_year() -> None:
    """Before the configured switch year, the year dispatcher routes to the forfaitair regime."""
    assert tax(investments=100000, actual=11800, year=2027) == 877.89


def test_dispatcher_uses_regime_b_from_the_switch_year() -> None:
    """From the configured switch year onward, the year dispatcher routes to the WWR regime."""
    assert tax(investments=100000, actual=11800, year=2028) == 3600.00


def test_pushing_the_switch_year_out_keeps_regime_a() -> None:
    """The 'forfaitair continues' scenario is regime_switch_year=9999."""
    never = CFG.model_copy(update={"regime_switch_year": 9999})
    assert tax(investments=100000, actual=11800, year=2050, cfg=never) == 877.89


def test_regime_b_requires_an_actual_return() -> None:
    """Regime B (WWR) fails loudly when no actual return is supplied, rather than assuming zero."""
    with pytest.raises(ValueError, match="actual_return"):
        tax(investments=100000, year=2028)


# --- per-person allowance for people who are not fiscal partners ---

ALEX, SAM = 1, 2


def _two_person_state(
    *, fiscal_partners: bool, year: int = 2026, gains: tuple[float, float] | None = None
) -> YearState:
    """Alex owns 100k of investments and a 10k debt, Sam 50k; the 20k bank is joint."""
    a = np.array
    alex = TreatmentMaps(balances={INVESTMENT: a([100_000.0]), DEBT: a([-10_000.0])})
    sam = TreatmentMaps(balances={INVESTMENT: a([50_000.0])})
    if gains is not None:
        alex.value_growth[INVESTMENT] = a([gains[0]])
        sam.value_growth[INVESTMENT] = a([gains[1]])
    joint = TreatmentMaps(balances={BANK: a([20_000.0])})
    return YearState(
        year=year,
        balances_by_treatment={
            BANK: a([20_000.0]),
            INVESTMENT: a([150_000.0]),
            DEBT: a([-10_000.0]),
        },
        investment_gain=None if gains is None else a([sum(gains)]),
        home_value=np.zeros(1),
        mortgage_interest_paid=np.zeros(1),
        fiscal_partners=fiscal_partners,
        by_owner={ALEX: alex, SAM: sam, None: joint},
    )


def test_allowance_per_person_hand_computed_for_non_partners() -> None:
    """Each non-partner pays on their own share with their own allowance and debt threshold."""
    # Alex: bank 10000 (half the joint 20000), investments 100000, debt 10000.
    #   eligible debt 10000 - 3800 = 6200; grondslag 110000 - 6200 = 103800
    #   rendement 10000*0.0128 + 100000*0.06 - 6200*0.027 = 128 + 6000 - 167.40 = 5960.60
    #   voordeel 5960.60 * (103800 - 59357)/103800 = 2552.09; tax * 0.36 = 918.75
    # Sam: bank 10000, investments 50000, no debt. grondslag 60000
    #   rendement 128 + 3000 = 3128; voordeel 3128 * 643/60000 = 33.52; tax 12.07
    # Pooled with one allowance (the old behaviour) this was 2086.24.
    got = NLTaxRegime().annual_investment_tax(_two_person_state(fiscal_partners=False), CFG)
    assert got[0] == pytest.approx(918.75 + 12.07, abs=0.005)


def test_allowance_for_fiscal_partners_is_unchanged() -> None:
    """Partners stay pooled: double allowance and double debt threshold on the joint base."""
    # eligible debt 10000 - 7600 = 2400; grondslag 170000 - 2400 = 167600
    # rendement 20000*0.0128 + 150000*0.06 - 2400*0.027 = 256 + 9000 - 64.80 = 9191.20
    # voordeel 9191.20 * (167600 - 118714)/167600 = 2680.91; tax 965.13
    got = NLTaxRegime().annual_investment_tax(_two_person_state(fiscal_partners=True), CFG)
    assert got[0] == pytest.approx(965.13, abs=0.005)


def test_allowance_stays_pooled_without_ownership_data() -> None:
    """With no ownership recorded the household is one taxpayer, as before."""
    s = replace(_two_person_state(fiscal_partners=False), by_owner={})
    got = NLTaxRegime().annual_investment_tax(s, CFG)
    assert got[0] == pytest.approx(2086.24, abs=0.005)


def test_allowance_per_person_applies_the_tegenbewijs_to_each_own_return() -> None:
    """Each non-partner compares their own actual return with their own forfaitair income."""
    # Alex's actual return 1000 < forfaitair 2552.09 -> 1000 * 0.36 = 360.00
    # Sam's actual return 5000 > forfaitair 33.52 -> keeps 12.07
    s = _two_person_state(fiscal_partners=False, gains=(1000.0, 5000.0))
    got = NLTaxRegime().annual_investment_tax(s, CFG)
    assert got[0] == pytest.approx(360.00 + 12.07, abs=0.005)


def test_allowance_per_person_under_the_wwr_does_not_net_one_loss_against_another_gain() -> None:
    """Under the WWR each non-partner gets their own allowance and keeps their own loss."""
    # Alex: (5000 - 1800) * 0.36 = 1152.00; Sam's 2000 loss offsets nothing of Alex's gain.
    s = _two_person_state(fiscal_partners=False, year=2028, gains=(5000.0, -2000.0))
    got = NLTaxRegime().annual_investment_tax(s, CFG)
    assert got[0] == pytest.approx(1152.00, abs=0.005)


# --- WWR verliesverrekening (Wet IB 2001 art. 5.65 and 5.67 as proposed in Kamerstuk 36748) ---


def _wwr_state(year: int, gain: list[float], *, partners: bool = False) -> YearState:
    """One taxpayer (or a partner pair) whose investments returned `gain`, one entry per run."""
    n = len(gain)
    return YearState(
        year=year,
        balances_by_treatment={INVESTMENT: np.full(n, 100_000.0)},
        investment_gain=np.array(gain),
        home_value=np.zeros(n),
        mortgage_interest_paid=np.zeros(n),
        fiscal_partners=partners,
    )


def _charge_years(states: list[YearState]) -> list[np.ndarray]:
    """Close each year in turn, keeping the composite as the engine does."""
    regime = HouseholdTax(residence=NLTaxRegime())
    taxes = []
    for s in states:
        due, regime = regime.close_year(s, CFG)
        taxes.append(due)
    return taxes


def test_wwr_loss_is_carried_forward_against_a_later_gain() -> None:
    """A loss year followed by a gain year costs less than the same gain on its own."""
    # 2028: -20000 -> loss 20000 - 500 = 19500. 2029: income 10000 - 1800 = 8200, all
    # offset. Without the loss: 8200 * 0.36 = 2952.
    with_loss = _charge_years([_wwr_state(2028, [-20_000.0]), _wwr_state(2029, [10_000.0])])
    without = _charge_years([_wwr_state(2028, [0.0]), _wwr_state(2029, [10_000.0])])
    assert with_loss[1][0] == 0.0
    assert without[1][0] == pytest.approx(2952.00, abs=0.005)


def test_wwr_loss_threshold_keeps_only_the_excess_over_500() -> None:
    """Art. 5.65: a negative income is a loss only for the part above 500."""
    # -1000 -> loss 500; 2029: (8200 - 500) * 0.36 = 2772.
    taxes = _charge_years([_wwr_state(2028, [-1000.0]), _wwr_state(2029, [10_000.0])])
    assert taxes[1][0] == pytest.approx(2772.00, abs=0.005)
    # -500 is not above the threshold: no loss, the full 2952 is due.
    taxes = _charge_years([_wwr_state(2028, [-500.0]), _wwr_state(2029, [10_000.0])])
    assert taxes[1][0] == pytest.approx(2952.00, abs=0.005)


def test_wwr_loss_is_used_up_over_several_years_and_does_not_expire() -> None:
    """Art. 5.67: offset against the following years, without a time limit."""
    # Loss 20000. 2029 and 2030 each use 8200, leaving 3600; 2031: (8200 - 3600) * 0.36.
    states = [_wwr_state(2028, [-20_500.0])] + [
        _wwr_state(y, [10_000.0]) for y in (2029, 2030, 2031, 2032)
    ]
    taxes = [t[0] for t in _charge_years(states)]
    assert taxes == pytest.approx([0.0, 0.0, 0.0, 1656.00, 2952.00], abs=0.005)


def test_wwr_loss_pool_is_per_run() -> None:
    """Monte Carlo runs keep their own pools: one run's crash does not shelter another."""
    taxes = _charge_years(
        [_wwr_state(2028, [-20_000.0, 10_000.0]), _wwr_state(2029, [10_000.0, 10_000.0])]
    )
    assert taxes[1] == pytest.approx([0.0, 2952.00], abs=0.005)


def test_wwr_loss_is_offset_after_the_allowance() -> None:
    """Art. 5.1: the loss reduces income, which is the result less the heffingsvrij resultaat."""
    # Loss 1000. 2029 result 2000 -> income 200 -> taxable 0, 800 left.
    # 2030 result 3000 -> income 1200 - 800 = 400 -> 144.
    taxes = _charge_years(
        [_wwr_state(2028, [-1500.0]), _wwr_state(2029, [2000.0]), _wwr_state(2030, [3000.0])]
    )
    assert [t[0] for t in taxes] == pytest.approx([0.0, 0.0, 144.00], abs=0.005)


def test_a_regime_a_year_leaves_no_wwr_loss() -> None:
    """Losses exist only under the WWR: a bad 2027 does not shelter 2028."""
    taxes = _charge_years([_wwr_state(2027, [-20_000.0]), _wwr_state(2028, [10_000.0])])
    assert taxes[1][0] == pytest.approx(2952.00, abs=0.005)


def test_wwr_fiscal_partners_share_one_loss_threshold() -> None:
    """A joint loss goes to one partner, so only one 500 threshold comes off it."""
    # -1000 -> loss 500, not 0; 2029: (10000 - 2 x 1800 - 500) * 0.36 = 2124.
    taxes = _charge_years(
        [_wwr_state(2028, [-1000.0], partners=True), _wwr_state(2029, [10_000.0], partners=True)]
    )
    assert taxes[1][0] == pytest.approx(2124.00, abs=0.005)


def test_wwr_losses_stay_with_the_non_partner_who_made_them() -> None:
    """People who are not fiscal partners each carry their own loss."""
    # 2028: Alex -20000 (loss 19500), Sam 0. 2029: Alex 0, Sam 10000 -> Sam pays 2952.
    # 2030: Alex 10000 -> offset in full.
    taxes = _charge_years(
        [
            _two_person_state(fiscal_partners=False, year=2028, gains=(-20_000.0, 0.0)),
            _two_person_state(fiscal_partners=False, year=2029, gains=(0.0, 10_000.0)),
            _two_person_state(fiscal_partners=False, year=2030, gains=(10_000.0, 0.0)),
        ]
    )
    assert [t[0] for t in taxes] == pytest.approx([0.0, 2952.00, 0.0], abs=0.005)
