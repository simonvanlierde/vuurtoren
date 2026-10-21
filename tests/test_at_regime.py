"""Austrian regime: figures, the realization tax, and a live NL -> AT residence change.

The point of AT in this repo is that it is shaped nothing like NL — a realization tax
with no wealth tax — so these tests lean on the differences rather than mirroring
`test_regime.py`.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from vuurtoren.domain import (
    Account,
    AccountKind,
    CashFlow,
    CashFlowKind,
    ChangeTaxResidence,
    Household,
    Milestone,
    Person,
)
from vuurtoren.engine import Assumptions, PlanInput, _open_run, _step_up_basis, project
from vuurtoren.tax.at.config import ATTaxConfig
from vuurtoren.tax.at.regime import BANK, INVESTMENT, NONREPORTING, PENSION, ATTaxRegime
from vuurtoren.tax.config import defaults_for
from vuurtoren.tax.regime import TaxRegime, YearState

CFG = defaults_for("AT", 2026, expect=ATTaxConfig)
TODAY = date(2026, 1, 1)


def _zeros(n: int = 1) -> np.ndarray:
    return np.zeros(n)


def _state(**kwargs: object) -> YearState:
    base = {
        "year": 2026,
        "balances_by_treatment": {},
        "home_value": _zeros(),
        "mortgage_interest_paid": _zeros(),
        "fiscal_partners": False,
    }
    return YearState(**{**base, **kwargs})  # ty: ignore[invalid-argument-type]


# --- the figures ---


def test_2026_figures_match_the_published_rates() -> None:
    """The shipped Austrian figures match what BMF and BMJ publish."""
    assert CFG.kest_rate == Decimal("0.275")
    assert CFG.grunderwerbsteuer_rate == Decimal("0.035")
    assert CFG.land_register_fee_rate == Decimal("0.011")


def test_the_austrian_regime_satisfies_the_protocol() -> None:
    """A second country drops into the seam without the protocol changing."""
    assert isinstance(ATTaxRegime(), TaxRegime)
    assert ATTaxRegime().country == "AT"


# --- what makes AT a realization tax ---


def test_there_is_no_annual_tax_on_holding_investments() -> None:
    """Austria abolished the Vermoegensteuer in 1994 — holding is not a taxable event.

    This is the single biggest difference from Box 3, and the reason the milestone is
    worth modelling at all.
    """
    s = _state(balances_by_treatment={INVESTMENT: np.array([1_000_000.0])})
    np.testing.assert_array_equal(ATTaxRegime().annual_investment_tax(s, CFG), _zeros())


def test_kest_is_charged_on_the_gain_not_on_the_gross_withdrawal() -> None:
    """27.5% of the profit. Taxing the gross would tax the return of capital."""
    charge = ATTaxRegime().withdrawal_tax(
        np.array([40_000.0]),
        treatment=INVESTMENT,
        realized_gain=np.array([10_000.0]),
        owner_person_id=None,
        year=2026,
        cfg=CFG,
    )
    assert charge[0] == pytest.approx(2_750.0)


def test_a_sale_at_or_below_cost_is_not_taxed() -> None:
    """No gain, no KESt — and a loss is floored at zero, never credited.

    Austrian capital losses offset gains within the same year only and are never carried
    forward, so the engine's per-sale charge must not go negative and quietly refund tax.
    """
    charge = ATTaxRegime().withdrawal_tax(
        np.array([40_000.0, 40_000.0]),
        treatment=INVESTMENT,
        realized_gain=np.array([0.0, -5_000.0]),
        owner_person_id=None,
        year=2026,
        cfg=CFG,
    )
    np.testing.assert_array_equal(charge, np.zeros(2))


def test_only_investments_are_taxed_on_the_way_out() -> None:
    """A pension withdrawal is not a KESt event."""
    charge = ATTaxRegime().withdrawal_tax(
        np.array([40_000.0]),
        treatment=PENSION,
        realized_gain=np.array([10_000.0]),
        owner_person_id=None,
        year=2026,
        cfg=CFG,
    )
    assert charge[0] == 0.0


def test_a_taxed_investment_wrapper_is_still_a_sweep_destination() -> None:
    """The two treatment sets must differ for AT, which is why they were split apart."""
    r = ATTaxRegime()
    assert INVESTMENT in r.withdrawal_taxed_treatments()
    assert INVESTMENT not in r.sweep_excluded_treatments()
    assert PENSION in r.sweep_excluded_treatments()


# --- housing and pension ---


def test_owning_a_home_has_no_annual_tax_effect() -> None:
    """No mortgage-interest deduction and no imputed rent, so the adjustment is zero."""
    s = _state(home_value=np.array([600_000.0]), mortgage_interest_paid=np.array([12_000.0]))
    np.testing.assert_array_equal(ATTaxRegime().annual_housing_adjustment(s, CFG), _zeros())


def test_purchase_costs_are_grunderwerbsteuer_plus_the_registration_fee() -> None:
    """3.5% + 1.1% = 4.6%, with no starter relief to consume."""
    duty, consumed = ATTaxRegime().purchase_costs(
        Decimal(500_000),
        buyer_age=28,
        starter_exemption_used=False,
        mortgage_amount=Decimal(0),
        cfg=CFG,
    )
    assert duty == Decimal("23000.00")
    assert consumed is False


def test_a_young_first_time_buyer_gets_no_relief_in_austria() -> None:
    """There is no startersvrijstelling equivalent — age must not change the answer."""
    young, _ = ATTaxRegime().purchase_costs(
        Decimal(300_000),
        buyer_age=25,
        starter_exemption_used=False,
        mortgage_amount=Decimal(0),
        cfg=CFG,
    )
    older, _ = ATTaxRegime().purchase_costs(
        Decimal(300_000),
        buyer_age=55,
        starter_exemption_used=True,
        mortgage_amount=Decimal(0),
        cfg=CFG,
    )
    assert young == older


def test_the_pension_age_is_a_flat_65_and_ignores_the_aow_drift() -> None:
    """Austria's 65 is statutory and unindexed, unlike the AOW."""
    r = ATTaxRegime()
    assert r.state_pension_date(date(1990, 6, 15), growth=0) == date(2055, 6, 15)
    # The household's AOW-drift assumption must not reach Austria's flat age.
    assert r.state_pension_date(date(1990, 6, 15), growth=3) == date(2055, 6, 15)


def test_a_gift_is_entirely_tax_free() -> None:
    """Austria abolished Schenkungssteuer in 2008, so nothing is above the exemption."""
    assert ATTaxRegime().gift_tax_free_amount(
        Decimal(500_000),
        recipient_birth_date=date(1990, 1, 1),
        gift_date=date(2026, 6, 1),
        onetime_used=True,
        cfg=CFG,
    ) == Decimal(500_000)


# --- the milestone this all exists for ---


def _vienna_plan() -> PlanInput:
    """A household that moves NL -> AT after two years, holding a gain-rich portfolio."""
    return PlanInput(
        household=Household(id=1, name="Test", tax_country="NL", fiscal_partners=False),
        people=[Person(id=1, household_id=1, name="A", birth_date=date(1990, 1, 1))],
        accounts=[
            Account(
                id=1,
                household_id=1,
                name="Cash",
                kind=AccountKind.CASH,
                tax_treatment="nl.box3_bank",
                manual_value=Decimal(20_000),
            ),
            Account(
                id=2,
                household_id=1,
                name="Equity",
                kind=AccountKind.EQUITY,
                tax_treatment="nl.box3_investment",
                manual_value=Decimal(400_000),
                cost_basis=Decimal(200_000),
                # A growing portfolio on purpose: with a flat one the Dutch actual
                # return is zero, the tegenbewijs elects, and Box 3 comes out at zero —
                # which would make "the wealth tax stopped" pass for the wrong reason.
                return_assumption=0.06,
            ),
        ],
        cash_flows=[
            CashFlow(
                id=1,
                household_id=1,
                label="salary",
                amount_monthly=Decimal(5_000),
                kind=CashFlowKind.INCOME,
                inflation_linked=False,
            ),
            CashFlow(
                id=2,
                household_id=1,
                label="spending",
                amount_monthly=Decimal(3_000),
                kind=CashFlowKind.EXPENSE,
                inflation_linked=False,
            ),
        ],
        milestones=[
            Milestone(
                id=1,
                household_id=1,
                label="Vienna",
                on_date=date(2028, 1, 1),
                params=ChangeTaxResidence(country="AT", retag=_TO_AT),
            )
        ],
        start=TODAY,
        assumptions=Assumptions(inflation=0.0),
    )


def test_moving_to_vienna_switches_regime_and_stops_the_wealth_tax() -> None:
    """The end-to-end milestone: NL Box 3 while here, nothing annual once in Austria.

    The accounts are retagged to `at.*` at the move. With no distribution yield on the
    portfolio, Austria has nothing annual to charge, so what this pins is that the
    *regime* switched, which is what `ChangeTaxResidence` promises.
    """
    p = project(_vienna_plan())
    per_year = p.tax_paid["investment_tax"][0]
    # 2026 and 2027 are Dutch years; from 2028 the household is Austrian.
    assert per_year[0] > 0.0, "the Dutch wealth tax should be charged before the move"
    assert per_year[1] > 0.0
    np.testing.assert_allclose(per_year[2:], 0.0, atol=1e-9)


_TO_AT = {1: "at.bank", 2: "at.investment"}
_TO_NL = {1: "nl.box3_bank", 2: "nl.box3_investment"}


def _drawdown(plan: PlanInput, country: str, treatments: dict[int, str]) -> PlanInput:
    """`plan` as a spending-only household of `country`, so its portfolio must be sold."""
    return replace(
        plan,
        household=plan.household.model_copy(update={"tax_country": country}),
        accounts=[a.model_copy(update={"tax_treatment": treatments[a.id]}) for a in plan.accounts],
        cash_flows=[f for f in plan.cash_flows if f.kind is CashFlowKind.EXPENSE],
    )


def _move(country: str, retag: dict[int, str] | None = None) -> Milestone:
    return Milestone(
        id=1,
        household_id=1,
        label=f"Move to {country}",
        on_date=TODAY,
        params=ChangeTaxResidence(country=country, retag=retag or {}),
    )


def test_a_retagged_move_to_vienna_charges_kest_on_the_drawdown() -> None:
    """After the move the Austrian regime taxes the accounts, retagged at the move month.

    Before `retag` existed the accounts kept their `nl.*` keys, which Austria does not
    know, so a household selling to live paid no KESt at all after moving.
    """
    plan = _drawdown(_vienna_plan(), "NL", _TO_NL)
    moved = project(replace(plan, milestones=[_move("AT", _TO_AT)]))
    native = project(_drawdown(plan, "AT", _TO_AT))
    assert float(moved.tax_paid["withdrawal_tax"][0].sum()) > 0.0
    np.testing.assert_allclose(
        moved.tax_paid["withdrawal_tax"][0], native.tax_paid["withdrawal_tax"][0], rtol=1e-9
    )


def test_a_retagged_move_back_to_the_netherlands_charges_box_3() -> None:
    """The reverse direction: `at.*` accounts retagged to `nl.*` pay Box 3 after AT -> NL."""
    plan = _drawdown(_vienna_plan(), "AT", _TO_AT)
    moved = project(replace(plan, milestones=[_move("NL", _TO_NL)]))
    assert float(moved.tax_paid["investment_tax"][0].sum()) > 0.0


def test_a_move_that_leaves_an_account_untagged_for_the_new_country_is_refused() -> None:
    """A treatment the target regime does not know would be taxed as nothing, silently."""
    plan = _drawdown(_vienna_plan(), "NL", _TO_NL)
    with pytest.raises(ValueError, match=r"Move to AT.*Equity"):
        project(replace(plan, milestones=[_move("AT", {1: "at.bank"})]))


def test_a_move_cannot_retag_an_account_the_plan_does_not_hold() -> None:
    """A retag aimed at an unknown account id fails rather than being ignored."""
    plan = _drawdown(_vienna_plan(), "NL", _TO_NL)
    with pytest.raises(ValueError, match="unknown account"):
        project(replace(plan, milestones=[_move("AT", {**_TO_AT, 99: "at.bank"})]))


def test_a_projection_that_starts_in_austria_never_charges_a_wealth_tax() -> None:
    """A wholly Austrian household pays nothing on merely holding its portfolio."""
    plan = _vienna_plan()
    # Spending only, so the household must sell to live and KESt actually fires. The
    # Vienna plan is a net saver, which would prove nothing about the withdrawal side.
    drawdown = [f for f in plan.cash_flows if f.kind is CashFlowKind.EXPENSE]
    austrian = PlanInput(
        household=Household(id=1, name="Test", tax_country="AT", fiscal_partners=False),
        people=plan.people,
        accounts=[
            a.model_copy(update={"tax_treatment": t})
            for a, t in zip(plan.accounts, ["at.bank", "at.investment"], strict=True)
        ],
        cash_flows=drawdown,
        milestones=[],
        start=plan.start,
        assumptions=plan.assumptions,
    )
    p = project(austrian)
    np.testing.assert_allclose(p.tax_paid["investment_tax"][0], 0.0, atol=1e-9)
    # But funding the spending by selling does trigger KESt on the gain.
    assert p.tax_paid["withdrawal_tax"][0].sum() > 0.0


# --- income taxed while still holding (ausschuettungsgleiche Ertraege) ---


def test_income_earned_while_holding_is_taxed_even_though_nothing_was_sold() -> None:
    """A reporting fund's deemed distribution falls due annually, accumulating or not.

    This is the half of Austrian tax that is *not* realization-based, and the reason
    `annual_investment_tax` exists for AT at all.
    """
    s = _state(income_by_treatment={INVESTMENT: np.array([10_000.0])})
    charge = ATTaxRegime().annual_investment_tax(s, CFG)
    assert charge[0] == pytest.approx(2_750.0)


def test_bank_interest_is_taxed_at_25_not_275() -> None:
    """Deposits with a credit institution keep the lower legacy rate."""
    s = _state(income_by_treatment={BANK: np.array([1_000.0])})
    charge = ATTaxRegime().annual_investment_tax(s, CFG)
    assert charge[0] == pytest.approx(250.0)


def test_the_two_buckets_are_charged_at_their_own_rates_together() -> None:
    """A household with both pays 27.5% on securities and 25% on the deposit."""
    s = _state(income_by_treatment={INVESTMENT: np.array([10_000.0]), BANK: np.array([1_000.0])})
    assert ATTaxRegime().annual_investment_tax(s, CFG)[0] == pytest.approx(3_000.0)


def test_taxed_income_raises_the_basis_so_it_is_not_taxed_again_on_sale() -> None:
    """The anti-double-taxation rule, § 186 Abs 3 InvFG.

    Deemed-distributed income was already taxed while held; without the step-up the same
    euro is taxed a second time as a capital gain when the fund is finally sold.
    """
    s = _state(income_by_treatment={INVESTMENT: np.array([10_000.0]), BANK: np.array([1_000.0])})
    step_up = ATTaxRegime().annual_basis_step_up(s, CFG)
    # The securities income steps up basis; the deposit's interest does not.
    assert set(step_up) == {INVESTMENT}
    assert step_up[INVESTMENT][0] == pytest.approx(10_000.0)


def test_holding_alone_is_still_never_taxed() -> None:
    """A portfolio that throws off no income owes nothing, however large."""
    s = _state(balances_by_treatment={INVESTMENT: np.array([5_000_000.0])})
    np.testing.assert_array_equal(ATTaxRegime().annual_investment_tax(s, CFG), _zeros())


# --- purchase costs on two bases ---


def test_the_mortgage_registration_fee_is_charged_on_the_debt_not_the_price() -> None:
    """GrESt and the Eintragungsgebuehr follow the price; the Pfandrecht follows the loan."""
    cash_buy, _ = ATTaxRegime().purchase_costs(
        Decimal(500_000),
        buyer_age=40,
        starter_exemption_used=False,
        mortgage_amount=Decimal(0),
        cfg=CFG,
    )
    financed, _ = ATTaxRegime().purchase_costs(
        Decimal(500_000),
        buyer_age=40,
        starter_exemption_used=False,
        mortgage_amount=Decimal(400_000),
        cfg=CFG,
    )
    assert cash_buy == Decimal("23000.00")  # 4.6% of the price only
    assert financed - cash_buy == Decimal("4800.00")  # 1.2% of the 400k registered


# --- the pension age now reaches the women's cohorts ---


def test_the_womens_transition_is_not_modelled_and_errs_late() -> None:
    """A cohort whose statutory age is below 65 still gets 65 — a stated omission.

    Born March 1966, Austrian law gives a woman 62 and a half. Modelling that cost a
    `Person.sex` field that never survived a database round-trip, so it is deliberately
    not modelled; see `tax/at/pension.py`. Erring late understates readiness rather than
    overstating it, which is the safe direction.
    """
    r = ATTaxRegime()

    assert r.state_pension_date(date(1966, 3, 1), growth=0) == date(2031, 3, 1)


# --- the second limb: gains the fund realises for itself ---


def test_a_funds_own_realized_gains_are_taxed_at_sixty_percent() -> None:
    """§ 186 Abs 2 InvFG deems 60% of a fund's realised gains distributed, not all of it.

    The holder sold nothing; the fund traded its own book. Income is passed through in
    full, gains only at 60%, so the two cannot share one input.
    """
    s = _state(fund_realized_gains_by_treatment={INVESTMENT: np.array([10_000.0])})
    charge = ATTaxRegime().annual_investment_tax(s, CFG)
    assert charge[0] == pytest.approx(10_000.0 * 0.60 * 0.275)


def test_income_and_fund_gains_are_taxed_on_their_own_fractions() -> None:
    """100% of income plus 60% of realised gains, both at 27.5%."""
    s = _state(
        income_by_treatment={INVESTMENT: np.array([4_000.0])},
        fund_realized_gains_by_treatment={INVESTMENT: np.array([10_000.0])},
    )
    expected = (4_000.0 + 10_000.0 * 0.60) * 0.275
    assert ATTaxRegime().annual_investment_tax(s, CFG)[0] == pytest.approx(expected)


def test_both_limbs_step_up_the_basis() -> None:
    """Everything deemed distributed was taxed, so all of it raises the cost basis."""
    s = _state(
        income_by_treatment={INVESTMENT: np.array([4_000.0])},
        fund_realized_gains_by_treatment={INVESTMENT: np.array([10_000.0])},
    )
    step_up = ATTaxRegime().annual_basis_step_up(s, CFG)
    assert step_up[INVESTMENT][0] == pytest.approx(4_000.0 + 10_000.0 * 0.60)


# --- non-reporting funds ---


def test_a_non_reporting_fund_is_taxed_on_ninety_percent_of_its_rise() -> None:
    """The lump-sum estimate replaces what the fund actually earned."""
    s = _state(
        balances_by_treatment={NONREPORTING: np.array([100_000.0])},
        value_growth_by_treatment={NONREPORTING: np.array([20_000.0])},
    )
    # 90% of 20,000 beats the 10%-of-100,000 floor.
    assert ATTaxRegime().annual_investment_tax(s, CFG)[0] == pytest.approx(20_000.0 * 0.90 * 0.275)


def test_a_non_reporting_fund_pays_the_floor_even_in_a_losing_year() -> None:
    """The 10% minimum is unconditional — this is what makes the treatment punitive."""
    s = _state(
        balances_by_treatment={NONREPORTING: np.array([100_000.0])},
        value_growth_by_treatment={NONREPORTING: np.array([-30_000.0])},
    )
    assert ATTaxRegime().annual_investment_tax(s, CFG)[0] == pytest.approx(100_000.0 * 0.10 * 0.275)


def test_a_non_reporting_fund_is_estimated_instead_of_measured_not_as_well_as() -> None:
    """Its reported income must not be charged on top of the lump-sum estimate."""
    estimated_only = _state(
        balances_by_treatment={NONREPORTING: np.array([100_000.0])},
        value_growth_by_treatment={NONREPORTING: np.array([20_000.0])},
    )
    also_reporting = _state(
        balances_by_treatment={NONREPORTING: np.array([100_000.0])},
        value_growth_by_treatment={NONREPORTING: np.array([20_000.0])},
        income_by_treatment={NONREPORTING: np.array([2_000.0])},
    )
    r = ATTaxRegime()
    assert r.annual_investment_tax(estimated_only, CFG)[0] == pytest.approx(
        r.annual_investment_tax(also_reporting, CFG)[0]
    )


def test_a_non_reporting_fund_is_still_taxed_on_the_gain_when_sold() -> None:
    """The lump-sum estimate is an annual charge, not a substitute for KESt at sale."""
    charge = ATTaxRegime().withdrawal_tax(
        np.array([40_000.0]),
        treatment=NONREPORTING,
        realized_gain=np.array([10_000.0]),
        owner_person_id=None,
        year=2026,
        cfg=CFG,
    )
    assert charge[0] == pytest.approx(2_750.0)


def test_a_reporting_fund_is_unaffected_by_the_lump_sum_rule() -> None:
    """An ordinary UCITS holder must not be swept into the punitive treatment."""
    s = _state(
        balances_by_treatment={INVESTMENT: np.array([100_000.0])},
        value_growth_by_treatment={INVESTMENT: np.array([20_000.0])},
    )
    np.testing.assert_array_equal(ATTaxRegime().annual_investment_tax(s, CFG), _zeros())


def test_the_lump_sum_estimate_is_what_raises_the_basis() -> None:
    """A non-reporting fund's basis steps up by the estimate it was actually taxed on.

    Charging the punitive lump sum and then stepping the basis up by the fund's raw
    reported income taxes the difference a second time at sale.
    """
    s = _state(
        balances_by_treatment={NONREPORTING: np.array([100_000.0])},
        value_growth_by_treatment={NONREPORTING: np.array([20_000.0])},
    )
    r = ATTaxRegime()
    step_up = r.annual_basis_step_up(s, CFG)[NONREPORTING]
    assert step_up[0] == pytest.approx(18_000.0)
    # The base the annual charge was computed on, recovered from the charge itself.
    assert r.annual_investment_tax(s, CFG)[0] == pytest.approx(step_up[0] * float(CFG.kest_rate))


def test_each_fund_s_step_up_lands_on_that_fund() -> None:
    """A non-reporting fund's lump-sum estimate raises its own basis, not its neighbour's.

    A reporting fund (2,000 of income) beside a non-reporting one (18,000 estimated from
    its 20,000 rise): the step-up was one household figure, split by reported income, so
    all 20,000 landed on the reporting fund. Selling both then taxed the non-reporting
    fund's 20,000 rise in full a second time.
    """
    plan = PlanInput(
        household=Household(id=1, name="T", tax_country="AT"),
        people=[Person(id=1, household_id=1, name="A", birth_date=date(1990, 1, 1))],
        accounts=[
            Account(
                id=1,
                household_id=1,
                name="Cash",
                kind=AccountKind.CASH,
                tax_treatment=BANK,
                manual_value=Decimal(1_000),
            ),
            Account(
                id=2,
                household_id=1,
                name="UCITS",
                kind=AccountKind.EQUITY,
                tax_treatment=INVESTMENT,
                manual_value=Decimal(100_000),
            ),
            Account(
                id=3,
                household_id=1,
                name="US ETF",
                kind=AccountKind.EQUITY,
                tax_treatment=NONREPORTING,
                manual_value=Decimal(100_000),
            ),
        ],
        cash_flows=[],
        milestones=[],
        start=TODAY,
    )
    run = _open_run(plan, n_runs=1, tax_overrides=None, regime=None)
    run.tax_year.income[2] = np.array([2_000.0])
    run.tax_year.growth[2] = np.array([8_000.0])
    run.tax_year.growth[3] = np.array([20_000.0])
    s = _state(
        balances_by_treatment={
            INVESTMENT: np.array([100_000.0]),
            NONREPORTING: np.array([100_000.0]),
        },
        income_by_treatment={INVESTMENT: np.array([2_000.0])},
        value_growth_by_treatment={
            INVESTMENT: np.array([8_000.0]),
            NONREPORTING: np.array([20_000.0]),
        },
    )
    _step_up_basis(run, run.regime.annual_basis_step_up(s, CFG))
    assert float(run.basis[2][0]) == pytest.approx(102_000.0)
    assert float(run.basis[3][0]) == pytest.approx(118_000.0)


def _austrian_plan(*, cash_yield: float = 0.0) -> PlanInput:
    """A wholly Austrian household that must sell to live, so KESt actually fires."""
    plan = _vienna_plan()
    return PlanInput(
        household=Household(id=1, name="Test", tax_country="AT", fiscal_partners=False),
        people=plan.people,
        accounts=[
            plan.accounts[0].model_copy(
                update={"tax_treatment": "at.none", "distribution_yield": cash_yield}
            ),
            plan.accounts[1].model_copy(
                # A reporting fund with a deemed distribution, so there is a step-up to
                # misallocate in the first place.
                update={"tax_treatment": "at.investment", "distribution_yield": 0.02}
            ),
        ],
        cash_flows=[f for f in plan.cash_flows if f.kind is CashFlowKind.EXPENSE],
        milestones=[],
        start=plan.start,
        assumptions=plan.assumptions,
    )


def test_an_untaxed_yielding_account_does_not_absorb_the_basis_step_up() -> None:
    """The step-up belongs to the accounts whose withdrawal the regime taxes.

    An `at.none` account earns income the Austrian regime never charges, so it creates no
    acquisition cost. Spreading part of the step-up onto it starves the investment
    account's basis and overstates the KESt due at sale.
    """
    quiet = project(_austrian_plan())
    yielding = project(_austrian_plan(cash_yield=0.03))
    assert float(quiet.tax_paid["withdrawal_tax"][0].sum()) > 0.0
    assert float(yielding.tax_paid["withdrawal_tax"][0].sum()) == pytest.approx(
        float(quiet.tax_paid["withdrawal_tax"][0].sum())
    )


def _non_reporting_plan(fund_yield: float) -> PlanInput:
    plan = _austrian_plan()
    fund = plan.accounts[1].model_copy(
        update={"tax_treatment": NONREPORTING, "distribution_yield": fund_yield}
    )
    return replace(plan, accounts=[plan.accounts[0], fund])


def test_a_non_reporting_fund_without_reported_yields_still_steps_up_its_basis() -> None:
    """The lump-sum estimate is charged whatever the fund reports, so it must raise the basis.

    The step-up used to be split only across accounts with a declared yield, so a
    non-reporting fund reporting nothing had its estimate charged every year and then the
    same euros charged again as gain at sale. A vanishing yield must not change the answer.
    """
    silent = project(_non_reporting_plan(0.0))
    trace = project(_non_reporting_plan(1e-9))
    assert float(silent.tax_paid["withdrawal_tax"][0].sum()) > 0.0
    assert float(silent.tax_paid["withdrawal_tax"][0].sum()) == pytest.approx(
        float(trace.tax_paid["withdrawal_tax"][0].sum()), abs=0.01
    )


def test_a_return_trip_reopens_the_dutch_actual_return_base() -> None:
    """NL -> AT -> NL: the first Dutch year back is taxed on that year's gain only.

    Austria counts no actual-return base, so the base carried out of the Austrian years
    was zero and the first December back taxed the whole portfolio as one year's gain.
    """
    plan = _vienna_plan()
    back = Milestone(
        id=2,
        household_id=1,
        label="back home",
        on_date=date(2029, 1, 1),
        params=ChangeTaxResidence(country="NL", retag=_TO_NL),
    )
    trip = project(replace(plan, milestones=[*plan.milestones, back]))
    stayed = project(replace(plan, milestones=[]))
    # 2029 is the fourth tax year. The two households differ only by the two Dutch
    # years of tax the traveller skipped, so the 2029 charges agree to within a few %.
    assert float(trip.tax_paid["investment_tax"][0, 3]) == pytest.approx(
        float(stayed.tax_paid["investment_tax"][0, 3]), rel=0.05
    )
