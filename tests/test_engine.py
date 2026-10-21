"""Engine-level tests: projection mechanics, tax wiring, FIRE metrics and the cash sweep."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from itertools import pairwise
from unittest import mock

import numpy as np
import pytest

import vuurtoren.engine
from vuurtoren.domain import (
    Account,
    AccountKind,
    BuyProperty,
    CashFlow,
    CashFlowKind,
    ChangeTaxResidence,
    Household,
    LumpSumIn,
    Milestone,
    Person,
    ScenarioOverrides,
)
from vuurtoren.engine import (
    Assumptions,
    PlanInput,
    _buffer_target,
    project,
    projection_months,
)
from vuurtoren.mortgage import annuity_payment
from vuurtoren.tax.config import TaxConfigBase, defaults_for  # a stub annotates it
from vuurtoren.tax.nl.config import NLTaxConfig
from vuurtoren.tax.nl.regime import NLTaxRegime
from vuurtoren.tax.overlay import PersonSlice  # noqa: TC001  # same
from vuurtoren.tax.regime import (
    YearState,  # noqa: TC001  # a stub annotates it; PEP 649 defers it anyway
)

TODAY = date(2026, 1, 1)

# Tests that isolate one mechanic pin the buffer off: with no expense flows the
# months-mode target is 6 x 0 = 0, so the sweep would move every euro of cash into
# equity and change the Box 3 base out from under whatever the test is measuring.
NO_SWEEP = Assumptions(cash_buffer_mode="off")


def simple_plan(**overrides: object) -> PlanInput:
    """Build a minimal two-account PlanInput (10k cash, 100k equity), fields overridable."""
    household = Household(id=1, name="T", fiscal_partners=False, life_expectancy_age=95)
    people = [Person(id=1, household_id=1, name="A", birth_date=date(1990, 1, 1))]
    accounts = [
        Account(
            id=1,
            household_id=1,
            owner_person_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(10000),
            return_assumption=0.0,
        ),
        Account(
            id=2,
            household_id=1,
            owner_person_id=1,
            name="Equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.box3_investment",
            manual_value=Decimal(100000),
            cost_basis=Decimal(100000),
            return_assumption=0.06,
        ),
    ]
    base = {
        "household": household,
        "people": people,
        "accounts": accounts,
        "cash_flows": [],
        "milestones": [],
        "start": TODAY,
        "assumptions": Assumptions(),
    }
    return PlanInput(**(base | overrides))  # ty: ignore[invalid-argument-type]


def test_the_horizon_runs_to_the_youngest_persons_life_expectancy() -> None:
    """I1: `min(birth_date)` picks the earliest-born (oldest) person, not the youngest.

    A 40-year age gap makes the bug obvious: the household must project to the
    younger person's 95th birthday year, not stop when they are only 55.
    """
    household = Household(id=1, name="T", fiscal_partners=False, life_expectancy_age=95)
    people = [
        Person(id=1, household_id=1, name="Older", birth_date=date(1960, 1, 1)),
        Person(id=2, household_id=1, name="Younger", birth_date=date(2000, 1, 1)),
    ]
    accounts = [
        Account(
            id=1,
            household_id=1,
            owner_person_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(10000),
            return_assumption=0.0,
        )
    ]
    plan = PlanInput(
        household=household,
        people=people,
        accounts=accounts,
        cash_flows=[],
        milestones=[],
        start=TODAY,
    )
    p = project(plan)
    # younger born 2000, life expectancy 95 -> ends 2095. n_months + 1 records: an
    # opening balance at index 0 plus each month's closing position (Task: index-0).
    assert len(p.months) == (2095 - 2026) * 12 + 1
    assert p.months[-1] == date(2095, 1, 1)


def test_the_horizon_ends_in_the_birth_month_of_the_life_expectancy_year() -> None:
    """Someone born in November lives to November of their last year, not to January.

    The horizon used to stop in January of the life-expectancy year whatever the birth
    month, which cut up to eleven months off the end of a late-born person's life.
    """
    late_born = [Person(id=1, household_id=1, name="A", birth_date=date(1990, 11, 15))]
    p = project(simple_plan(people=late_born))
    assert p.months[-1] == date(2085, 11, 1)
    assert len(p.months) == (2085 - 2026) * 12 + 10 + 1
    assert projection_months(simple_plan(people=late_born)) == p.months


def test_projection_has_one_row_per_month_to_life_expectancy() -> None:
    """The projection runs one row per month from plan.start to the life-expectancy year."""
    p = project(simple_plan())
    # born 1990, life expectancy 95 -> ends 2085. n_months + 1 records: an opening
    # balance at index 0 plus each month's closing position (Task: index-0).
    assert len(p.months) == (2085 - 2026) * 12 + 1
    assert p.net_worth.shape == (1, len(p.months))


def test_index_zero_is_the_true_opening_balance_before_any_growth() -> None:
    """Known finding 1: growth was applied before recording, so index 0 was one month ahead.

    months[0] is plan.start ("today"); the recorded net worth there must equal the raw
    opening balances, with no growth or flows applied yet.
    """
    p = project(simple_plan())
    assert p.months[0] == TODAY
    assert np.isclose(p.net_worth[0, 0], 10000 + 100000)
    assert np.isclose(p.components["cash"][0, 0], 10000.0)
    assert np.isclose(p.components["liquid_investments"][0, 0], 100000.0)


def test_a_static_plan_grows_at_the_return_assumption() -> None:
    """With no flows, equity compounds at return_assumption/12 monthly, net of wealth tax."""
    p = project(simple_plan(assumptions=NO_SWEEP))
    # 100000 equity at 6% nominal for one year, monthly compounded, plus 10000 flat cash,
    # minus the wealth tax charged at the December 2026 boundary (Task 13). Index 12,
    # not 11: index 0 is the opening balance, so "after a year" (12 months) is index 12.
    after_a_year = p.net_worth[0, 12]
    expected = 10000 + 100000 * (1 + 0.06 / 12) ** 12 - p.tax_paid["investment_tax"][0, 0]
    assert np.isclose(after_a_year, expected, rtol=1e-9)


def test_expense_ratio_drags_the_return() -> None:
    """A fund's TER comes off the monthly gross return as expense_ratio/12."""
    base = simple_plan(assumptions=NO_SWEEP)
    equity = base.accounts[1].model_copy(update={"expense_ratio": 0.005})
    p = project(simple_plan(assumptions=NO_SWEEP, accounts=[base.accounts[0], equity]))
    after_a_year = p.net_worth[0, 12]
    expected = (
        10000 + 100000 * (1 + 0.06 / 12 - 0.005 / 12) ** 12 - p.tax_paid["investment_tax"][0, 0]
    )
    assert np.isclose(after_a_year, expected, rtol=1e-9)


def test_inflation_factor_tracks_the_price_level() -> None:
    """inflation_factor is the cumulative price level: 1.0 at start, (1+inflation) a year on."""
    p = project(simple_plan(assumptions=Assumptions(inflation=0.02, cash_buffer_mode="off")))
    assert p.inflation_factor.shape[0] == len(p.months)
    assert np.isclose(p.inflation_factor[0], 1.0)
    assert np.isclose(p.inflation_factor[12], 1.02, rtol=1e-9)


def test_zero_return_accounts_do_not_move() -> None:
    """An account with return_assumption=0.0 keeps the same balance month to month."""
    plan = simple_plan(assumptions=NO_SWEEP)
    p = project(plan)
    assert np.isclose(p.components["cash"][0, 0], 10000.0)
    # November: no growth applied and no annual tax charged yet (that lands in December).
    assert np.isclose(p.components["cash"][0, 10], 10000.0)


def test_income_minus_expenses_accumulates_in_cash() -> None:
    """Monthly income minus expenses accumulates directly in the cash account."""
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="salary",
            amount_monthly=Decimal(3000),
            kind=CashFlowKind.INCOME,
            inflation_linked=False,
        ),
        CashFlow(
            id=2,
            household_id=1,
            label="rent",
            amount_monthly=Decimal(1200),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        ),
    ]
    p = project(simple_plan(cash_flows=flows, assumptions=NO_SWEEP))
    # minus the wealth tax charged at the December 2026 boundary (Task 13). Index 12,
    # not 11: index 0 is the opening balance, so after twelve months is index 12.
    expected = 10000 + 12 * 1800 - p.tax_paid["investment_tax"][0, 0]
    assert np.isclose(p.components["cash"][0, 12], expected)


def test_a_flow_targeting_an_unknown_account_fails_the_pre_flight() -> None:
    """`balances[target] += ...` would KeyError mid-run — say so before anything moves.

    The API's own FK stops this at the boundary, so the pre-flight is what covers every
    other way a plan reaches the engine: a scenario override, a seeded document, a
    direct `project()`.
    """
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="DCA",
            amount_monthly=Decimal(500),
            kind=CashFlowKind.CONTRIBUTION,
            target_account_id=999,
            inflation_linked=False,
        )
    ]
    with pytest.raises(ValueError, match="999"):
        project(simple_plan(cash_flows=flows))


def test_contributions_route_into_the_target_account() -> None:
    """A CONTRIBUTION flow's amount routes into its target_account_id, not into cash."""
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="salary",
            amount_monthly=Decimal(3000),
            kind=CashFlowKind.INCOME,
            inflation_linked=False,
        ),
        CashFlow(
            id=2,
            household_id=1,
            label="DCA",
            amount_monthly=Decimal(1000),
            kind=CashFlowKind.CONTRIBUTION,
            target_account_id=2,
            inflation_linked=False,
        ),
    ]
    p = project(simple_plan(cash_flows=flows))
    equity_only = project(simple_plan()).components["liquid_investments"][0, 11]
    assert p.components["liquid_investments"][0, 11] > equity_only


def test_inflation_linked_flows_grow() -> None:
    """An inflation_linked expense leaves less cash than an otherwise identical flat one."""
    flat = CashFlow(
        id=1,
        household_id=1,
        label="rent",
        amount_monthly=Decimal(1200),
        kind=CashFlowKind.EXPENSE,
        inflation_linked=False,
    )
    linked = CashFlow(
        id=1,
        household_id=1,
        label="rent",
        amount_monthly=Decimal(1200),
        kind=CashFlowKind.EXPENSE,
        inflation_linked=True,
    )
    a = project(simple_plan(cash_flows=[flat])).components["cash"][0, -1]
    b = project(simple_plan(cash_flows=[linked])).components["cash"][0, -1]
    assert b < a


def test_flows_respect_their_start_and_end_dates() -> None:
    """A cash flow only affects cash between its start_date and end_date, not outside it."""
    flow = CashFlow(
        id=1,
        household_id=1,
        label="bonus",
        amount_monthly=Decimal(1000),
        kind=CashFlowKind.INCOME,
        inflation_linked=False,
        start_date=date(2027, 1, 1),
        end_date=date(2027, 12, 31),
    )
    p = project(simple_plan(cash_flows=[flow], assumptions=NO_SWEEP))
    # Each December boundary charges wealth tax (Task 13); subtract what has accrued so far.
    # Index 0 is the opening balance, so "after N months" is index N, not N - 1.
    tax = p.tax_paid["investment_tax"][0]
    assert np.isclose(p.components["cash"][0, 12], 10000.0 - tax[:1].sum())  # not yet started
    assert np.isclose(p.components["cash"][0, 24], 10000.0 + 12000.0 - tax[:2].sum())
    assert np.isclose(p.components["cash"][0, 36], 10000.0 + 12000.0 - tax[:3].sum())  # ended


def test_components_sum_to_net_worth() -> None:
    """The values of p.components sum exactly to p.net_worth for every month and run."""
    p = project(simple_plan())
    total = sum(p.components.values())
    assert np.allclose(total, p.net_worth)


def test_a_debt_account_reduces_net_worth_and_box3_tax() -> None:
    """Task 1: DEBT balances are stored negative and the deduction reaches the regime."""
    debt = Account(
        id=3,
        household_id=1,
        owner_person_id=1,
        name="Loan",
        kind=AccountKind.DEBT,
        tax_treatment="nl.box3_debt",
        manual_value=Decimal(-50000),
        return_assumption=0.0,
    )
    p = project(simple_plan(accounts=[*simple_plan().accounts, debt]))
    assert np.isclose(p.net_worth[0, 0], 10000 + 100000 - 50000)
    assert np.isclose(p.components["debt"][0, 0], -50000)
    # Year-1 wealth tax is strictly lower than the same plan without the debt account,
    # proving the Box 3 debt deduction reaches the regime through the engine.
    without_debt = project(simple_plan())
    assert p.tax_paid["investment_tax"][0, 0] < without_debt.tax_paid["investment_tax"][0, 0]


def test_n_runs_broadcasts_identically_without_volatility() -> None:
    """With n_runs > 1 and no volatility, every run's net worth is identical."""
    p = project(simple_plan(), n_runs=5)
    assert p.net_worth.shape == (5, len(p.months))
    assert np.allclose(p.net_worth[0], p.net_worth[4])


def _with_a_young_buyer(plan: PlanInput) -> PlanInput:
    """`plan` with its person born in 2000, young enough for the starter exemption.

    The exemption stops at 35, which simple_plan's person (born 1990) has passed by the
    projection start.
    """
    young = plan.people[0].model_copy(update={"birth_date": date(2000, 1, 1)})
    return replace(plan, people=[young])


def buy_house_plan(price: str = "360000", when: date = date(2028, 6, 1)) -> PlanInput:
    """Build a simple_plan with a BuyProperty milestone at the given price and date."""
    m = Milestone(
        id=1,
        household_id=1,
        label="Buy",
        on_date=when,
        params=BuyProperty(
            price=Decimal(price),
            mortgage=Decimal(price) - Decimal(20000),
            annual_rate=Decimal("0.042"),
            term_months=360,
            buyer_person_id=1,
        ),
    )
    plan = simple_plan()
    return PlanInput(
        household=plan.household,
        people=plan.people,
        accounts=plan.accounts,
        cash_flows=plan.cash_flows,
        milestones=[m],
        start=plan.start,
        assumptions=plan.assumptions,
    )


def test_buying_a_house_creates_home_equity_and_debt() -> None:
    """A BuyProperty milestone creates positive home_equity and negative debt from purchase."""
    p = project(buy_house_plan())
    # Index 0 is the opening balance; the purchase happens while processing the 2028-06
    # month (calc index 29), so its effect first shows in the closing record at 30.
    i = 30
    assert p.components["home_equity"][0, i] > 0
    assert p.components["debt"][0, i] < 0


def test_buying_a_house_lowers_box_3_tax() -> None:
    """The primary residence leaves the Box 3 base.

    Compared in 2027, still under the forfaitair regime (default regime_switch_year
    2028). From 2028 the household is under the WWR regime, which taxes only the
    year's actual investment gain and never looks at cash/bank balances at all — so a
    lower cash balance from the deposit has no effect there, and the comparison must
    stay in a forfaitair year to be meaningful.
    """
    renting = project(simple_plan())
    buying = project(buy_house_plan(when=date(2026, 6, 1)))
    year_index = 2027 - 2026
    assert (
        buying.tax_paid["investment_tax"][0, year_index]
        < renting.tax_paid["investment_tax"][0, year_index]
    )


def test_the_mortgage_amortises_to_zero() -> None:
    """A mortgage's debt balance amortises to zero by the end of its term."""
    p = project(buy_house_plan(when=date(2027, 1, 1)))
    assert np.isclose(p.components["debt"][0, -1], 0.0, atol=1.0)


def test_the_final_mortgage_payment_does_not_overcharge_cash() -> None:
    """C2: on the last month, only interest + capped principal leaves cash.

    A 12-month term means the last scheduled payment slightly overshoots the
    remaining balance (the annuity payment is rounded to the cent, the engine's
    float loop is not), so `principal` is capped below `payment - interest`. The
    amount deducted from cash that month must be `interest + principal`, not the
    full annuity-sized payment, or the household is charged a few cents it never
    owed. Reference total mirrors the engine's own float/no-cent-rounding
    convention (not box1's Decimal one) so the two are comparable to machine
    precision, isolating exactly the deduction-cap bug from unrelated rounding
    noise.
    """
    price, mortgage, rate = Decimal(360000), Decimal(340000), Decimal("0.042")
    payment = float(annuity_payment(mortgage, rate, 12))
    rate_f = float(rate)

    balance = float(mortgage)
    total_interest = 0.0
    total_principal = 0.0
    for _ in range(12):
        interest = balance * rate_f / 12
        principal = min(payment - interest, balance)
        balance = max(balance - principal, 0.0)
        total_interest += interest
        total_principal += principal
    assert balance == 0.0
    correct_total_spent = total_interest + total_principal
    buggy_total_spent = payment * 12  # what the old code deducted: full payment x 12 months
    assert buggy_total_spent - correct_total_spent > 0.01  # the bug is real, not noise

    m = Milestone(
        id=1,
        household_id=1,
        label="Buy",
        on_date=date(2026, 1, 1),
        params=BuyProperty(
            price=price, mortgage=mortgage, annual_rate=rate, term_months=12, buyer_person_id=1
        ),
    )
    plan = simple_plan(assumptions=NO_SWEEP)
    plan = PlanInput(
        household=plan.household,
        people=plan.people,
        accounts=plan.accounts,
        cash_flows=plan.cash_flows,
        milestones=[m],
        start=plan.start,
        assumptions=plan.assumptions,
    )
    # Zero the wealth tax and the HRA benefit so neither contaminates the cash
    # comparison below (buying a house already changes both, unrelated to this test).
    no_tax = {"NL": {2026: {"box3_rate": Decimal(0), "hra_max_rate": Decimal(0)}}}
    p = project(plan, tax_overrides=no_tax)
    # Index 0 is the opening balance; after twelve months processed the position is at
    # index 12 (Task: index-0).
    assert np.isclose(p.components["debt"][0, 12], 0.0, atol=1.0)
    assert p.tax_paid["housing_adjustment"][0, 0] == 0.0
    assert p.tax_paid["investment_tax"][0, 0] == 0.0

    deposit = price - mortgage
    duty = Decimal(str(p.one_off_costs["transfer_tax"][0]))

    cash_no_house = project(simple_plan(assumptions=NO_SWEEP), tax_overrides=no_tax).components[
        "cash"
    ][0, 12]
    cash_with_house = p.components["cash"][0, 12]
    actual_total_spent = float(cash_no_house - cash_with_house) - float(deposit) - float(duty)

    assert np.isclose(actual_total_spent, correct_total_spent, atol=0.01, rtol=0.0)
    assert not np.isclose(actual_total_spent, buggy_total_spent, atol=0.01, rtol=0.0)


def test_a_starter_purchase_under_the_cap_pays_no_transfer_tax() -> None:
    """A purchase under the starter-exemption cap pays no transfer tax, one above it does."""
    cheap = project(_with_a_young_buyer(buy_house_plan(price="360000")))
    dear = project(_with_a_young_buyer(buy_house_plan(price="600000")))
    assert cheap.one_off_costs["transfer_tax"][0] == 0.0
    assert dear.one_off_costs["transfer_tax"][0] > 0.0


def test_a_non_own_occupancy_purchase_is_rejected() -> None:
    """own_occupancy=False must fail loudly, not be silently modelled as a primary residence.

    The engine only models a primary residence: it folds every purchase into home_value
    (Box 1). A non-primary residence belongs in Box 3, which the engine cannot model.
    The 8% general rate itself is still covered at the regime seam.
    """
    m = Milestone(
        id=1,
        household_id=1,
        label="Buy to let",
        on_date=date(2028, 6, 1),
        params=BuyProperty(
            price=Decimal(500000),
            mortgage=Decimal(480000),
            annual_rate=Decimal("0.042"),
            term_months=360,
            buyer_person_id=1,
            own_occupancy=False,
        ),
    )
    plan = simple_plan()
    plan = PlanInput(
        household=plan.household,
        people=plan.people,
        accounts=plan.accounts,
        cash_flows=plan.cash_flows,
        milestones=[m],
        start=plan.start,
        assumptions=plan.assumptions,
    )
    with pytest.raises(NotImplementedError, match="Box 3"):
        project(plan)


def test_a_first_purchase_above_the_cap_does_not_consume_the_starter_exemption() -> None:
    """A disqualifying first purchase (over cap or over-age) must not burn the starter exemption.

    That leaves it available for a later qualifying purchase. Both mortgages are zero,
    so the single-mortgage guard does not fire.
    """
    first = Milestone(
        id=1,
        household_id=1,
        label="Buy 1 (over cap)",
        on_date=date(2027, 1, 1),
        params=BuyProperty(
            price=Decimal(600000),
            mortgage=Decimal(0),
            annual_rate=Decimal("0.042"),
            term_months=360,
            buyer_person_id=1,
        ),
    )
    second = Milestone(
        id=2,
        household_id=1,
        label="Buy 2 (under cap)",
        on_date=date(2029, 1, 1),
        params=BuyProperty(
            price=Decimal(360000),
            mortgage=Decimal(0),
            annual_rate=Decimal("0.042"),
            term_months=360,
            buyer_person_id=1,
        ),
    )
    plan = simple_plan()
    plan = PlanInput(
        household=plan.household,
        people=plan.people,
        accounts=plan.accounts,
        cash_flows=plan.cash_flows,
        milestones=[first, second],
        start=plan.start,
        assumptions=plan.assumptions,
    )
    p = project(_with_a_young_buyer(plan))
    # First (600k, age 27, over cap): 2% = 12000, exemption NOT consumed.
    # Second (360k, age 29, under cap): starter exemption still available -> 0.
    # The bug charged 12000 + 7200 by consuming the exemption on the first buy.
    assert p.one_off_costs["transfer_tax"][0] == 12000.0


def test_an_unknown_buyer_person_id_is_rejected() -> None:
    """A non-None buyer_person_id with no matching person raises rather than silently defaulting.

    buyer_person_id=None keeps the people[0] default, but falling back to people[0] for
    an unmatched id could silently flip the exemption age test.
    """
    m = Milestone(
        id=1,
        household_id=1,
        label="Buy",
        on_date=date(2028, 6, 1),
        params=BuyProperty(
            price=Decimal(360000),
            mortgage=Decimal(0),
            annual_rate=Decimal("0.042"),
            term_months=360,
            buyer_person_id=999,
        ),
    )
    plan = simple_plan()
    plan = PlanInput(
        household=plan.household,
        people=plan.people,
        accounts=plan.accounts,
        cash_flows=plan.cash_flows,
        milestones=[m],
        start=plan.start,
        assumptions=plan.assumptions,
    )
    with pytest.raises(ValueError, match="999"):
        project(plan)


def test_a_second_property_purchase_while_a_mortgage_is_outstanding_is_rejected() -> None:
    """C2: two simultaneous mortgages are out of scope; fail loudly, not with -EUR2.7M debt.

    Was test_a_second_property_purchase_pays_full_transfer_tax_via_the_regime, asserting
    a second purchase's transfer tax while a first mortgage (EUR340k) was still
    outstanding. That plan is exactly the unbounded negative amortisation repro from the
    review, so it must now raise instead of silently producing nonsense figures.
    """
    first = Milestone(
        id=1,
        household_id=1,
        label="Buy 1",
        on_date=date(2027, 1, 1),
        params=BuyProperty(
            price=Decimal(360000),
            mortgage=Decimal(340000),
            annual_rate=Decimal("0.042"),
            term_months=360,
            buyer_person_id=1,
        ),
    )
    second = Milestone(
        id=2,
        household_id=1,
        label="Buy 2",
        on_date=date(2028, 1, 1),
        params=BuyProperty(
            price=Decimal(500000),
            mortgage=Decimal(480000),
            annual_rate=Decimal("0.042"),
            term_months=360,
            buyer_person_id=1,
        ),
    )
    plan = simple_plan()
    plan = PlanInput(
        household=plan.household,
        people=plan.people,
        accounts=plan.accounts,
        cash_flows=plan.cash_flows,
        milestones=[first, second],
        start=plan.start,
        assumptions=plan.assumptions,
    )
    with pytest.raises(NotImplementedError):
        project(plan)


def test_box_3_tax_is_charged_annually() -> None:
    """Wealth tax is assessed once per calendar year covered by the projection, not monthly."""
    p = project(simple_plan())
    # p.months has one more entry than there are calculated months (the opening
    # balance at index 0 plus every month's closing position, Task: index-0); drop
    # the trailing label, which spills one month past the last tax year assessed.
    assert p.tax_paid["investment_tax"].shape[1] == len({m.year for m in p.months[:-1]})
    assert p.tax_paid["investment_tax"][0, 0] > 0.0


def test_a_scenario_override_changes_the_tax_charged() -> None:
    """A Scenario.overrides.tax entry raising box3_rate increases the wealth tax charged."""
    plan = simple_plan()
    baseline = project(plan)
    doubled = project(
        plan,
        tax_overrides={"NL": {2026: {"box3_rate": Decimal("0.72")}}},
    )
    assert (
        doubled.tax_paid["investment_tax"][0, 0] > baseline.tax_paid["investment_tax"][0, 0] * 1.9
    )


def test_a_scenario_override_does_not_leak_into_the_next_projection() -> None:
    """The tax config is memoised per projection, never across them."""
    plan = simple_plan()
    before = project(plan)
    project(
        plan,
        tax_overrides={"NL": {2026: {"box3_rate": Decimal("0.72")}}},
    )
    after = project(plan)
    np.testing.assert_array_equal(
        after.tax_paid["investment_tax"], before.tax_paid["investment_tax"]
    )


def test_the_regime_switch_changes_the_basis_in_2028() -> None:
    """Under regime B a flat year is untaxed; under regime A wealth alone is taxed."""
    plan = simple_plan()
    forfaitair_forever = project(
        plan,
        tax_overrides={"NL": {y: {"regime_switch_year": Decimal(9999)} for y in range(2026, 2092)}},
    )
    default = project(plan)
    year_index = 2030 - 2026
    assert (
        default.tax_paid["investment_tax"][0, year_index]
        != (forfaitair_forever.tax_paid["investment_tax"][0, year_index])
    )


def test_indexed_allowances_reduce_tax_growth() -> None:
    """index_tax_allowances=False freezes the box3 allowance, so tax grows faster over time."""
    plan = simple_plan()
    frozen = PlanInput(
        household=plan.household,
        people=plan.people,
        accounts=plan.accounts,
        cash_flows=plan.cash_flows,
        milestones=plan.milestones,
        start=plan.start,
        assumptions=Assumptions(index_tax_allowances=False),
    )
    assert (
        project(plan).tax_paid["investment_tax"][0, 20]
        < project(frozen).tax_paid["investment_tax"][0, 20]
    )


def test_the_first_tax_year_uses_the_shipped_allowance_unindexed() -> None:
    """Indexing runs from the config's own year, not the projection start.

    The shipped 2026 figures are already in 2026 euros, so the first December must use
    them as-is. Nothing else in this plan depends on inflation (no inflation-linked
    flows, buffer off), so the first year's tax must not move with the assumption.
    """
    inflated = project(simple_plan(assumptions=Assumptions(cash_buffer_mode="off", inflation=0.02)))
    flat = project(simple_plan(assumptions=Assumptions(cash_buffer_mode="off", inflation=0.0)))
    assert inflated.tax_paid["investment_tax"][0, 0] == flat.tax_paid["investment_tax"][0, 0]


def test_allowances_index_by_whole_years_from_the_config_year() -> None:
    """The second tax year indexes by exactly one year of inflation.

    Not by the number of months since the projection started.
    """
    inflated = project(simple_plan(assumptions=Assumptions(cash_buffer_mode="off", inflation=0.02)))
    shipped = defaults_for("NL", 2026, expect=NLTaxConfig)
    hand_indexed = project(
        simple_plan(assumptions=Assumptions(cash_buffer_mode="off", inflation=0.0)),
        tax_overrides={
            "NL": {
                2027: {
                    "box3_allowance_per_person": shipped.box3_allowance_per_person * Decimal("1.02")
                }
            }
        },
    )
    assert np.isclose(
        inflated.tax_paid["investment_tax"][0, 1],
        hand_indexed.tax_paid["investment_tax"][0, 1],
        rtol=1e-12,
    )


def test_a_stochastic_provider_reaches_zero_assumption_accounts() -> None:
    """A zero return_assumption must not short-circuit growth.

    A Monte Carlo provider can draw nonzero returns for an account whose mean is zero.
    """
    p = project(simple_plan(assumptions=NO_SWEEP), returns=lambda _account, _month, _n: 0.01)
    assert np.isclose(p.components["cash"][0, 1], 10000.0 * 1.01)


def pension_plan() -> PlanInput:
    """Build a simple_plan with an added PENSION account (lijfrente) unlocking in 2030."""
    plan = simple_plan()
    accounts = [
        *plan.accounts,
        Account(
            id=3,
            household_id=1,
            owner_person_id=1,
            name="Lijfrente",
            kind=AccountKind.PENSION,
            tax_treatment="nl.box1_pension",
            manual_value=Decimal(12000),
            return_assumption=0.0,
            liquid_from=date(2030, 1, 1),
        ),
    ]
    return PlanInput(
        household=plan.household,
        people=plan.people,
        accounts=accounts,
        cash_flows=plan.cash_flows,
        milestones=plan.milestones,
        start=plan.start,
        assumptions=plan.assumptions,
    )


def test_the_lijfrente_is_excluded_before_it_unlocks() -> None:
    """fire_usable excludes a locked pension account, even though net_worth includes it."""
    p = project(pension_plan())
    i = 47  # 2029-12, the month before liquid_from
    assert p.months[i] == date(2029, 12, 1)
    assert not np.isclose(p.fire.fire_usable[0, i], p.net_worth[0, i])
    assert np.isclose(
        p.fire.fire_usable[0, i],
        p.components["liquid_investments"][0, i] + p.components["cash"][0, i],
    )


def test_the_lijfrente_is_included_after_it_unlocks() -> None:
    """fire_usable includes a pension account from its liquid_from month onward."""
    p = project(pension_plan())
    i = 48  # 2030-01
    assert p.months[i] == date(2030, 1, 1)
    assert np.isclose(
        p.fire.fire_usable[0, i],
        p.components["liquid_investments"][0, i]
        + p.components["cash"][0, i]
        + p.components["pension"][0, i],
    )


def test_fire_usable_never_counts_home_equity() -> None:
    """fire_usable stays below net_worth once home_equity exists: it is never usable capital."""
    p = project(buy_house_plan())
    i = 40
    assert p.fire.fire_usable[0, i] < p.net_worth[0, i]


def test_fire_number_is_annual_expenses_over_the_swr() -> None:
    """fire_number equals annual expenses divided by the safe withdrawal rate."""
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="living",
            amount_monthly=Decimal(2000),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        )
    ]
    p = project(simple_plan(cash_flows=flows))
    assert np.isclose(p.fire.fire_number, 2000 * 12 / 0.04)


def test_fi_date_is_when_usable_capital_first_covers_the_fire_number() -> None:
    """fi_dates marks the first month fire_usable capital covers fire_number, not before."""
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="living",
            amount_monthly=Decimal(1000),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        )
    ]
    p = project(simple_plan(cash_flows=flows, assumptions=NO_SWEEP))
    assert p.fire.fi_dates[0] is not None
    i = p.months.index(p.fire.fi_dates[0])
    # A flat nominal expense needs a flat nominal pot: deflating both sides cancels.
    assert p.fire.fire_usable[0, i] >= p.fire.fire_number
    assert p.fire.fire_usable[0, i - 1] < p.fire.fire_number


def test_more_inflation_never_brings_fi_forward() -> None:
    """FI compares the pot and the FIRE number in the same (start-month) euros.

    Compared nominally, inflation grew the pot and left the target in 2026 euros, so at
    4% inflation FI came years earlier than at 0% — while the spending it must fund rose.
    """
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="salary",
            amount_monthly=Decimal(5000),
            kind=CashFlowKind.INCOME,
            inflation_linked=True,
        ),
        CashFlow(
            id=2,
            household_id=1,
            label="living",
            amount_monthly=Decimal(2500),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=True,
        ),
    ]

    def fi_at(inflation: float) -> date:
        assumptions = Assumptions(cash_buffer_mode="months", inflation=inflation)
        fi = project(simple_plan(cash_flows=flows, assumptions=assumptions)).fire.fi_dates[0]
        assert fi is not None
        return fi

    assert fi_at(0.04) >= fi_at(0.0)


def test_fi_date_is_none_when_the_plan_never_gets_there() -> None:
    """fi_dates is None for a plan whose expenses are too high to ever reach fire_number."""
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="living",
            amount_monthly=Decimal(50000),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        )
    ]
    p = project(simple_plan(cash_flows=flows))
    assert p.fire.fi_dates[0] is None


def test_savings_rate_is_saved_over_income() -> None:
    """savings_rate is (income - expenses) / income at plan start."""
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="salary",
            amount_monthly=Decimal(4000),
            kind=CashFlowKind.INCOME,
            inflation_linked=False,
        ),
        CashFlow(
            id=2,
            household_id=1,
            label="living",
            amount_monthly=Decimal(3000),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        ),
    ]
    p = project(simple_plan(cash_flows=flows))
    assert np.isclose(p.fire.savings_rate, 0.25)


def zero_return_accounts() -> list[Account]:
    """Build a cash + equity account pair, both with return_assumption=0.0."""
    return [
        Account(
            id=1,
            household_id=1,
            owner_person_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(10000),
            return_assumption=0.0,
        ),
        Account(
            id=2,
            household_id=1,
            owner_person_id=1,
            name="Equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.box3_investment",
            manual_value=Decimal(100000),
            cost_basis=Decimal(100000),
            return_assumption=0.0,
        ),
    ]


def test_wwr_does_not_tax_the_households_own_contributions_as_gains() -> None:
    """C1: routing cash into an investment account must not look like investment gain.

    All returns are zero, so with no real gain anywhere, a WWR year (from
    regime_switch_year=2028, here 2029) must charge identical wealth tax whether or
    not the household also moved its own after-tax cash from cash into equity.
    """
    no_contribution = project(simple_plan(accounts=zero_return_accounts()))

    contribution = CashFlow(
        id=1,
        household_id=1,
        label="DCA",
        amount_monthly=Decimal(1000),
        kind=CashFlowKind.CONTRIBUTION,
        target_account_id=2,
        inflation_linked=False,
    )
    with_contribution = project(
        simple_plan(accounts=zero_return_accounts(), cash_flows=[contribution])
    )

    year_index = 2029 - 2026
    assert (
        with_contribution.tax_paid["investment_tax"][0, year_index]
        == no_contribution.tax_paid["investment_tax"][0, year_index]
        == 0.0
    )


def test_a_milestone_dated_before_the_plan_start_is_rejected() -> None:
    """A milestone dated before `plan.start` raises instead of silently never firing.

    The up-front check only covered types; a date before `plan.start` would never
    match any `when` in the projection loop and so never fired, silently.
    """
    m = Milestone(
        id=1,
        household_id=1,
        label="Too early",
        on_date=date(2025, 6, 1),
        params=LumpSumIn(amount=Decimal(1000)),
    )
    plan = simple_plan(milestones=[m])
    with pytest.raises(ValueError, match="Too early"):
        project(plan)


def test_a_milestone_dated_past_the_horizon_is_rejected() -> None:
    """Same failure mode as the too-early case, at the other end of the window."""
    m = Milestone(
        id=1,
        household_id=1,
        label="Too late",
        on_date=date(2095, 1, 1),
        params=LumpSumIn(amount=Decimal(1000)),
    )
    plan = simple_plan(milestones=[m])
    with pytest.raises(ValueError, match="Too late"):
        project(plan)


def test_a_plan_that_runs_out_of_money_reports_the_month_it_happened() -> None:
    """cash_shortfall reports the first month cash went negative.

    The engine never liquidates investments to cover a shortfall, so an insolvent
    household keeps projecting against an implicit unlimited overdraft. Net worth
    stays plausible; only this flag says the plan already failed.
    """
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="salary",
            amount_monthly=Decimal(3000),
            kind=CashFlowKind.INCOME,
            inflation_linked=False,
        ),
        CashFlow(
            id=2,
            household_id=1,
            label="living",
            amount_monthly=Decimal(9000),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        ),
    ]
    p = project(simple_plan(cash_flows=flows))
    shortfall = p.cash_shortfall[0]
    assert shortfall is not None
    i = p.months.index(shortfall)
    assert p.components["cash"][0, i] < 0
    assert p.components["cash"][0, i - 1] >= 0


def test_a_solvent_plan_reports_no_shortfall() -> None:
    """cash_shortfall is [None] for a plan whose cash never goes negative."""
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="salary",
            amount_monthly=Decimal(3000),
            kind=CashFlowKind.INCOME,
            inflation_linked=False,
        )
    ]
    assert project(simple_plan(cash_flows=flows)).cash_shortfall == [None]


def test_fi_dates_are_reported_per_run_not_taken_from_run_zero() -> None:
    """With n_runs > 1 there is no single FI date.

    Reporting run 0's as the household's hid a multi-year spread behind one
    confident-looking number.
    """

    def split_returns(account: Account, _month: int, n_runs: int) -> np.ndarray:
        r = np.full(n_runs, account.return_assumption / 12)
        r[1:] *= 4.0  # runs 1+ compound far faster than run 0
        return r

    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="living",
            amount_monthly=Decimal(2500),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        )
    ]
    # No inflation: a flat nominal expense against a nominal return keeps run 0 reaching FI.
    flat = Assumptions(cash_buffer_mode="off", inflation=0.0)
    # Run 0 only gets there in the 2080s, so the horizon runs to 2091 (1990 + 101).
    long_lived = simple_plan().household.model_copy(update={"life_expectancy_age": 101})
    p = project(
        simple_plan(household=long_lived, cash_flows=flows, assumptions=flat),
        n_runs=3,
        returns=split_returns,
    )
    assert len(p.fire.fi_dates) == 3
    assert len(p.fire.coast_fire_dates) == 3
    assert p.fire.fi_dates[0] is not None
    assert p.fire.fi_dates[1] is not None
    assert p.fire.fi_dates[1] < p.fire.fi_dates[0]
    assert p.fire.fi_dates[1] == p.fire.fi_dates[2]


def test_the_cash_account_is_chosen_by_id_not_by_list_order() -> None:
    """`plan.accounts` arrives from an unordered query.

    With two CASH accounts of different tax_treatment, letting row order pick which
    one absorbs every flow moves the Box 3 base and so the tax.
    """
    second_cash = Account(
        id=3,
        household_id=1,
        owner_person_id=1,
        name="Untaxed cash",
        kind=AccountKind.CASH,
        tax_treatment="nl.none",
        manual_value=Decimal(10000),
        return_assumption=0.0,
    )
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="salary",
            amount_monthly=Decimal(3000),
            kind=CashFlowKind.INCOME,
            inflation_linked=False,
        )
    ]
    forwards = simple_plan(cash_flows=flows)
    accounts = [*forwards.accounts, second_cash]
    a = project(simple_plan(cash_flows=flows, accounts=accounts))
    b = project(simple_plan(cash_flows=flows, accounts=list(reversed(accounts))))
    assert np.allclose(a.tax_paid["investment_tax"], b.tax_paid["investment_tax"])
    assert np.allclose(a.net_worth, b.net_worth)


def test_a_plan_starting_under_the_wwr_regime_projects() -> None:
    """A start year at or past regime_switch_year (2028) no longer crashes.

    The first tax year used to have investment_gain=None and regime B refuses None.
    The gain base now opens at the projection start, so the first year is computable
    like any other.
    """
    plan = simple_plan()
    plan = PlanInput(
        household=plan.household,
        people=plan.people,
        accounts=plan.accounts,
        cash_flows=plan.cash_flows,
        milestones=plan.milestones,
        start=date(2028, 1, 1),
        assumptions=plan.assumptions,
    )
    p = project(plan)
    # 100000 at 6% nominal gains ~6167 in year one; WWR taxes it above the allowance.
    assert p.tax_paid["investment_tax"][0, 0] > 0.0


def test_the_first_year_elects_the_tegenbewijs_on_a_proven_flat_year() -> None:
    """A zero-return first year is a proven flat year, so the tegenbewijs zeroes the tax.

    Before the gain base opened at the projection start, year one was always
    forfaitair (gain unknown).
    """
    p = project(simple_plan(accounts=zero_return_accounts()))
    assert p.tax_paid["investment_tax"][0, 0] == 0.0


def test_fire_metrics_ignore_flows_that_are_not_active_at_the_start() -> None:
    """The FIRE number and savings rate are point-in-time figures at plan.start.

    An expense that already ended (or has not started) must not inflate them forever.
    """
    perm = CashFlow(
        id=1,
        household_id=1,
        label="living",
        amount_monthly=Decimal(1000),
        kind=CashFlowKind.EXPENSE,
        inflation_linked=False,
    )
    expired = CashFlow(
        id=2,
        household_id=1,
        label="finished childcare",
        amount_monthly=Decimal(2000),
        kind=CashFlowKind.EXPENSE,
        inflation_linked=False,
        start_date=date(2020, 1, 1),
        end_date=date(2025, 6, 30),
    )
    p = project(simple_plan(cash_flows=[perm, expired]))
    assert np.isclose(p.fire.fire_number, 1000 * 12 / 0.04)


def test_a_change_of_tax_residence_to_an_unknown_country_fails_up_front() -> None:
    """An unknown country fails up front rather than surfacing as a bare KeyError months in.

    The other milestone preconditions are checked before the loop; an unknown
    country must be too. Belgium, because AT is now implemented — a move to Vienna
    is exercised end-to-end in `test_at_regime.py`.
    """
    m = Milestone(
        id=1,
        household_id=1,
        label="Move to Brussels",
        on_date=date(2030, 1, 1),
        params=ChangeTaxResidence(country="BE"),
    )
    plan = simple_plan(milestones=[m])
    with pytest.raises(ValueError, match="Move to Brussels"):
        project(plan)


def test_a_horizon_that_ends_before_it_starts_is_rejected() -> None:
    """An impossible horizon raises with a clear message instead of a bare numpy error.

    Previously died inside numpy with "negative dimensions are not allowed", which
    said nothing about the birth date or life expectancy that caused it.
    """
    plan = simple_plan()
    plan = PlanInput(
        household=Household(id=1, name="T", fiscal_partners=False, life_expectancy_age=20),
        people=plan.people,
        accounts=plan.accounts,
        cash_flows=plan.cash_flows,
        milestones=plan.milestones,
        start=plan.start,
        assumptions=plan.assumptions,
    )
    with pytest.raises(ValueError, match="horizon ends before it starts"):
        project(plan)


# --- cash buffer configuration ---


def test_the_buffer_target_is_months_of_expenses_by_default() -> None:
    """_buffer_target defaults to a flat multiple of monthly expenses, no mortgage."""
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="living",
            amount_monthly=Decimal(2000),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        )
    ]
    plan = simple_plan(cash_flows=flows)
    assert _buffer_target(plan, TODAY, 1.0, 0.0) == pytest.approx(12000.0)


def test_the_buffer_target_counts_the_mortgage_payment() -> None:
    """_buffer_target adds the mortgage payment on top of ordinary expense flows.

    Rent is an ordinary EXPENSE flow and is already counted, so excluding the
    mortgage would give the buy scenario a smaller buffer than the rent scenario as a
    pure artefact — in the one comparison the app exists to answer.
    """
    plan = simple_plan()
    assert _buffer_target(plan, TODAY, 1.0, 1800.0) == pytest.approx(10800.0)


def test_the_buffer_target_inflates_only_the_flagged_flows() -> None:
    """It must use the same rule step 2 uses to debit, not a parallel one."""
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="indexed",
            amount_monthly=Decimal(1000),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=True,
        ),
        CashFlow(
            id=2,
            household_id=1,
            label="flat",
            amount_monthly=Decimal(1000),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        ),
    ]
    plan = simple_plan(cash_flows=flows)
    assert _buffer_target(plan, TODAY, 2.0, 0.0) == pytest.approx(6 * 3000.0)


def test_a_fixed_buffer_inflates_when_flagged_and_not_otherwise() -> None:
    """A fixed cash buffer inflates when cash_buffer_inflation_linked=True, else stays flat."""
    linked = simple_plan(
        assumptions=Assumptions(cash_buffer_mode="fixed", cash_buffer_fixed=Decimal(25000))
    )
    flat = simple_plan(
        assumptions=Assumptions(
            cash_buffer_mode="fixed",
            cash_buffer_fixed=Decimal(25000),
            cash_buffer_inflation_linked=False,
        )
    )
    assert _buffer_target(linked, TODAY, 2.0, 0.0) == pytest.approx(50000.0)
    assert _buffer_target(flat, TODAY, 2.0, 0.0) == pytest.approx(25000.0)


def test_an_expense_flow_outside_its_window_does_not_size_the_buffer() -> None:
    """An expense flow that already ended before plan.start contributes nothing to the buffer."""
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="ended",
            amount_monthly=Decimal(2000),
            kind=CashFlowKind.EXPENSE,
            end_date=date(2025, 12, 1),
            inflation_linked=False,
        )
    ]
    assert _buffer_target(simple_plan(cash_flows=flows), TODAY, 1.0, 0.0) == pytest.approx(0.0)


def test_scenario_assumption_overrides_can_carry_a_sweep_order() -> None:
    """ScenarioOverrides.assumptions can hold the sweep-order Literal, not just Decimal.

    It was previously dict[str, Decimal], which cannot hold the two Literal strings
    or the bool. Widening it is what makes the buffer scenario-editable at all, which
    is the whole reason it lives on Assumptions.
    """
    o = ScenarioOverrides(assumptions={"cash_sweep_order": "riskiest_first"})
    assert o.assumptions["cash_sweep_order"] == "riskiest_first"


# --- the sweep, wired up ---


def _spender_plan(**overrides: object) -> PlanInput:
    """Income well below expenses, so the buffer must sell to keep cash off the floor."""
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="salary",
            amount_monthly=Decimal(1000),
            kind=CashFlowKind.INCOME,
            inflation_linked=False,
        ),
        CashFlow(
            id=2,
            household_id=1,
            label="living",
            amount_monthly=Decimal(3000),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        ),
    ]
    return simple_plan(cash_flows=flows, **overrides)


def test_the_buffer_holds_cash_at_its_target_while_investments_remain() -> None:
    """The sweep holds cash at its computed target, not merely above zero.

    With only a "not negative" assertion, replacing the computed target with 0.0
    would pass the whole suite. _spender_plan's expenses are 3000/month and not
    inflation-linked, so the months-mode target is a flat 6 x 3000. Restricted to
    months where equity comfortably exceeds the shortfall, since the sweep is
    best-effort once the holdings run down.
    """
    projection = project(_spender_plan())
    # From index 1: index 0 is the opening position, recorded before any sweep runs.
    cash = projection.components["cash"][0][1:]
    equity = projection.components["liquid_investments"][0][1:]
    funded = equity > 20000.0
    assert funded.any()
    assert cash[funded].min() == pytest.approx(18000.0)


def test_the_sweep_is_best_effort_and_a_dry_plan_still_reports_a_shortfall() -> None:
    """The engine does not invent money: a dry plan still reports a cash shortfall.

    cash_shortfall stops meaning "nothing ever swept" and starts meaning "genuinely
    insolvent".
    """
    projection = project(_spender_plan())
    assert projection.cash_shortfall[0] is not None
    assert projection.components["liquid_investments"][0][-1] == pytest.approx(0.0, abs=1.0)


def test_turning_the_buffer_off_restores_the_sinking_cash_line() -> None:
    """cash_buffer_mode='off' lets cash run down instead of selling investments to refill it."""
    swept = project(_spender_plan())
    off = project(_spender_plan(assumptions=Assumptions(cash_buffer_mode="off")))
    assert off.components["cash"][0].min() < swept.components["cash"][0].min()
    assert off.components["liquid_investments"][0][-1] > 1000.0


def test_the_sweep_conserves_net_worth_in_the_month_it_runs() -> None:
    """Moving money between accounts is not income: the sweep must not change net worth.

    Compared against buffer-off in the first month, before the different Box 3 bases
    have had a year to diverge.
    """
    swept = project(_spender_plan())
    off = project(_spender_plan(assumptions=Assumptions(cash_buffer_mode="off")))
    assert swept.net_worth[0, 1] == pytest.approx(off.net_worth[0, 1], rel=1e-9)


def test_a_locked_pension_is_never_sold_to_refill_cash() -> None:
    """The classic bug. Both sides of the boundary month."""
    unlock = date(2036, 1, 1)
    accounts = [
        Account(
            id=1,
            household_id=1,
            owner_person_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(1000),
        ),
        Account(
            id=2,
            household_id=1,
            owner_person_id=1,
            name="Lijfrente",
            kind=AccountKind.PENSION,
            tax_treatment="nl.box1_pension",
            manual_value=Decimal(200000),
            liquid_from=unlock,
        ),
    ]
    projection = project(_spender_plan(accounts=accounts))
    before = projection.months.index(unlock) - 1
    after = projection.months.index(unlock) + 2
    assert projection.components["pension"][0, before] == pytest.approx(200000.0)
    # Sold once unlocked — and the Box 1 charge on the withdrawal appears in its own line.
    assert projection.components["pension"][0, after] < 200000.0
    assert projection.tax_paid["withdrawal_tax"][0, unlock.year - 2026] > 0.0


def test_no_withdrawal_tax_is_charged_before_the_pension_unlocks() -> None:
    """The charge must follow the sale, not merely the existence of a pension."""
    unlock = date(2036, 1, 1)
    accounts = [
        Account(
            id=1,
            household_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(1000),
        ),
        Account(
            id=2,
            household_id=1,
            name="Lijfrente",
            kind=AccountKind.PENSION,
            tax_treatment="nl.box1_pension",
            manual_value=Decimal(200000),
            liquid_from=unlock,
        ),
    ]
    projection = project(_spender_plan(accounts=accounts))
    charged = projection.tax_paid["withdrawal_tax"][0]
    assert charged[: unlock.year - 2026].sum() == pytest.approx(0.0)


class _AllowanceWatchingRegime(NLTaxRegime):
    """Records the box3 allowance the withdrawal step handed it, per year charged.

    NL's own withdrawal tax is a flat Rate and AT's is too, so no shipped country can
    tell an indexed config from an unindexed one on this path — which is exactly how it
    went unnoticed. This regime reads a Money field instead, so the difference shows.
    """

    def __init__(self) -> None:
        super().__init__()
        self.seen: dict[int, float] = {}

    def withdrawal_tax(
        self,
        amount: np.ndarray,
        *,
        treatment: str,
        realized_gain: np.ndarray,
        owner_person_id: int | None,
        year: int,
        cfg: NLTaxConfig,
    ) -> np.ndarray:
        self.seen[year] = float(cfg.box3_allowance_per_person)
        return super().withdrawal_tax(
            amount,
            treatment=treatment,
            realized_gain=realized_gain,
            owner_person_id=owner_person_id,
            year=year,
            cfg=cfg,
        )


def test_a_withdrawal_is_taxed_against_that_years_indexed_config() -> None:
    """The withdrawal step resolves its config the same way December's does.

    It used to call `resolve_tax_config` bare, so a withdrawal in 2036 was charged
    against figures still quoted in 2026 euros — a decade of bracket creep no assumption
    asked for. `index_tax_allowances` is the dial that says whether they follow
    inflation, and it has to reach here too.
    """
    unlock = date(2036, 1, 1)
    accounts = [
        Account(
            id=1,
            household_id=1,
            owner_person_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(1000),
        ),
        Account(
            id=2,
            household_id=1,
            owner_person_id=1,
            name="Lijfrente",
            kind=AccountKind.PENSION,
            tax_treatment="nl.box1_pension",
            manual_value=Decimal(200000),
            liquid_from=unlock,
        ),
    ]
    indexed, frozen = _AllowanceWatchingRegime(), _AllowanceWatchingRegime()
    project(_spender_plan(accounts=accounts), regime=indexed)
    project(
        _spender_plan(accounts=accounts, assumptions=Assumptions(index_tax_allowances=False)),
        regime=frozen,
    )
    assert unlock.year in indexed.seen
    assert indexed.seen[unlock.year] > frozen.seen[unlock.year]
    # A decade of 2% on the 2026 figure, not the 2026 figure itself.
    assert indexed.seen[unlock.year] == pytest.approx(
        frozen.seen[unlock.year] * 1.02 ** (unlock.year - 2026), rel=1e-9
    )


def test_selling_a_pension_nets_the_withdrawal_tax_off_the_proceeds() -> None:
    """A lijfrente uitkering is Box 1 income, so liquidating 100 does not deliver 100 of cash.

    Compared against an otherwise identical EQUITY holding, whose sale is not a
    taxable event at all under either modelled Box 3 regime.
    """

    def plan_with(kind: AccountKind, treatment: str) -> PlanInput:
        return _spender_plan(
            accounts=[
                Account(
                    id=1,
                    household_id=1,
                    name="Cash",
                    kind=AccountKind.CASH,
                    tax_treatment="nl.box3_bank",
                    manual_value=Decimal(1000),
                ),
                Account(
                    id=2,
                    household_id=1,
                    name="Pot",
                    kind=kind,
                    tax_treatment=treatment,
                    manual_value=Decimal(200000),
                ),
            ]
        )

    pension = project(plan_with(AccountKind.PENSION, "nl.box1_pension"))
    equity = project(plan_with(AccountKind.EQUITY, "nl.box3_investment"))
    i = 24
    assert pension.tax_paid["withdrawal_tax"][0].sum() > 0.0
    assert equity.tax_paid["withdrawal_tax"][0].sum() == pytest.approx(0.0)
    # The tax is real money leaving the household, so net worth must be lower.
    assert pension.net_worth[0, i] < equity.net_worth[0, i]


def test_surplus_cash_is_never_invested_into_a_pension() -> None:
    """The cash sweep never routes surplus cash into a PENSION account.

    Money must not flow into a wrapper that charges to come back out — and a real
    lijfrente has a jaarruimte limit the engine knows nothing about.
    """
    accounts = [
        Account(
            id=1,
            household_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(500000),
        ),
        Account(
            id=2,
            household_id=1,
            name="Lijfrente",
            kind=AccountKind.PENSION,
            tax_treatment="nl.box1_pension",
            manual_value=Decimal(10000),
        ),
    ]
    # No expense flows: the months target is 0, so every euro of cash is swept out —
    # and with the pension the only other account, it must all stay put in cash.
    projection = project(simple_plan(accounts=accounts))
    assert projection.components["pension"][0, 12] == pytest.approx(10000.0)
    assert projection.components["cash"][0, 12] == pytest.approx(500000.0)
    assert projection.tax_paid["withdrawal_tax"][0].sum() == pytest.approx(0.0)


def test_the_sell_order_changes_which_holding_drains_first() -> None:
    """The two orders must be distinguishable in the output.

    They differ in *which* account is drained, and a sweep conserves net worth — so
    with equal returns both orders would produce byte-identical projections and this
    test would pass vacuously. The low-volatility holding therefore also earns less, so
    draining it first (safest_first) leaves the higher-earning holding compounding and
    must end ahead.
    """
    accounts = [
        Account(
            id=1,
            household_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(1000),
        ),
        Account(
            id=2,
            household_id=1,
            name="Bonds",
            kind=AccountKind.BOND,
            tax_treatment="nl.box3_investment",
            manual_value=Decimal(50000),
            return_assumption=0.02,
            volatility_assumption=0.04,
        ),
        Account(
            id=3,
            household_id=1,
            name="Equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.box3_investment",
            manual_value=Decimal(50000),
            return_assumption=0.07,
            volatility_assumption=0.18,
        ),
    ]
    safest = project(
        _spender_plan(accounts=accounts, assumptions=Assumptions(cash_sweep_order="safest_first"))
    )
    riskiest = project(
        _spender_plan(accounts=accounts, assumptions=Assumptions(cash_sweep_order="riskiest_first"))
    )
    i = 24
    assert safest.net_worth[0, i] > riskiest.net_worth[0, i]


def test_shuffling_the_accounts_does_not_change_the_projection() -> None:
    """Two accounts at equal volatility sweep identically regardless of query row order.

    This is the tie-break test at engine level.
    """

    def make(order: list[int]) -> list[Account]:
        by_id = {
            2: Account(
                id=2,
                household_id=1,
                name="A",
                kind=AccountKind.EQUITY,
                tax_treatment="nl.box3_investment",
                manual_value=Decimal(30000),
                volatility_assumption=0.15,
            ),
            3: Account(
                id=3,
                household_id=1,
                name="B",
                kind=AccountKind.EQUITY,
                tax_treatment="nl.box3_investment",
                manual_value=Decimal(70000),
                volatility_assumption=0.15,
            ),
        }
        cash = Account(
            id=1,
            household_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(1000),
        )
        return [cash, *(by_id[i] for i in order)]

    assumptions = Assumptions(cash_sweep_order="safest_first")
    a = project(_spender_plan(accounts=make([2, 3]), assumptions=assumptions))
    b = project(_spender_plan(accounts=make([3, 2]), assumptions=assumptions))
    np.testing.assert_allclose(a.net_worth, b.net_worth)


def test_a_sweep_does_not_manufacture_an_investment_gain() -> None:
    """A cash sweep buying or selling investments must not read as an investment gain.

    Selling reduces the invested total and buying raises it; neither is a gain. From
    2028 the WWR regime taxes actual return only, so with zero returns every year's
    wealth tax must be exactly zero. Without the investment_net_inflow_this_year
    adjustment the monthly buy sweep reads as a gain and the tax goes positive.
    """
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="salary",
            amount_monthly=Decimal(5000),
            kind=CashFlowKind.INCOME,
            inflation_linked=False,
        )
    ]
    accounts = [
        Account(
            id=1,
            household_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(10000),
        ),
        Account(
            id=2,
            household_id=1,
            name="Equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.box3_investment",
            manual_value=Decimal(100000),
            cost_basis=Decimal(100000),
        ),
    ]
    # No expense flows, so the months target is 0 and every euro of cash is swept in.
    projection = project(simple_plan(cash_flows=flows, accounts=accounts))
    wwr_years = projection.tax_paid["investment_tax"][0, (2028 - 2026) :]
    np.testing.assert_allclose(wwr_years, 0.0, atol=1e-6)


def test_a_december_sweep_counts_against_the_following_year_not_the_current_one() -> None:
    """A December sweep is a flow of the *next* year, not a gain in the year it runs.

    The sweep runs after step 7 has reset the accumulator and set
    year_start_investments. Get the ordering wrong and the December movement is
    zeroed out, leaving a phantom gain in the following year.
    """
    accounts = [
        Account(
            id=1,
            household_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(100000),
        ),
        Account(
            id=2,
            household_id=1,
            name="Equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.box3_investment",
            manual_value=Decimal(100000),
            cost_basis=Decimal(100000),
        ),
    ]
    milestones = [
        Milestone(
            id=1,
            household_id=1,
            label="windfall",
            on_date=date(2030, 12, 1),
            params=LumpSumIn(amount=Decimal(200000)),
        )
    ]
    projection = project(
        simple_plan(
            accounts=accounts,
            milestones=milestones,
            assumptions=Assumptions(
                cash_buffer_mode="fixed",
                cash_buffer_fixed=Decimal(100000),
                cash_buffer_inflation_linked=False,
            ),
        )
    )
    for year in (2030, 2031):
        assert projection.tax_paid["investment_tax"][0, year - 2026] == pytest.approx(0.0, abs=1e-6)


def test_coast_fire_measures_to_the_retirement_age_not_to_life_expectancy() -> None:
    """The coasting runway ends at the coast target age, not at life expectancy.

    Capital that only reaches the FIRE number by compounding until the household is
    95 is not coasting.
    """
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="living",
            amount_monthly=Decimal(6700),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        )
    ]
    # fire_number = 6700 * 12 / 4% = 2,010,000. The 110k of capital at the 6% coast
    # return reaches ~949k by age 67 (37 years) but ~4.8M by the 95-year horizon —
    # so only measuring to life expectancy would call this household coasting.
    p = project(simple_plan(cash_flows=flows, assumptions=NO_SWEEP))
    assert p.fire.coast_fire_dates == [None]


def test_coast_fire_reports_capital_that_reaches_the_number_by_the_target_age() -> None:
    """coast_fire_dates reports today when capital already coasts to fire_number on its own."""
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="living",
            amount_monthly=Decimal(2000),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        ),
        CashFlow(
            id=2,
            household_id=1,
            label="salary",
            amount_monthly=Decimal(2500),
            kind=CashFlowKind.INCOME,
            inflation_linked=False,
        ),
    ]
    # fire_number = 600,000 and, with no inflation, 110k * 1.06^31 ~ 670k: today's capital
    # coasts there by age 67 (2057) on its own, so the coast date is the very first month.
    flat = Assumptions(cash_buffer_mode="off", inflation=0.0)
    p = project(simple_plan(cash_flows=flows, assumptions=flat))
    assert p.fire.coast_fire_dates == [TODAY]


def test_coasting_grows_at_the_real_return() -> None:
    """Coast-FIRE nets inflation out of `coast_return`, as FI nets it out of the pot.

    The plan above at 2% inflation: 110k coasts at (1.06 / 1.02)^31 ~ 3.3x to ~362k,
    short of 600,000, where the nominal 1.06^31 would have reached ~670k and coasted.
    """
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="living",
            amount_monthly=Decimal(2000),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=True,
        ),
        CashFlow(
            id=2,
            household_id=1,
            label="salary",
            amount_monthly=Decimal(2500),
            kind=CashFlowKind.INCOME,
            inflation_linked=False,
        ),
    ]
    p = project(simple_plan(cash_flows=flows, assumptions=NO_SWEEP))
    assert p.fire.coast_fire_dates != [TODAY]


def test_a_flat_nominal_expense_shrinks_the_real_target() -> None:
    """Only inflation-linked spending keeps its start-year size; a flat expense erodes.

    Deflating the pot alone would hold a non-linked expense to its start-year euros for
    ever, so at 4% inflation FI would come later than for the same plan at 0%.
    """
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="salary",
            amount_monthly=Decimal(5000),
            kind=CashFlowKind.INCOME,
            inflation_linked=False,
        ),
        CashFlow(
            id=2,
            household_id=1,
            label="rent",
            amount_monthly=Decimal(2500),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        ),
    ]

    def fi_at(inflation: float) -> date:
        assumptions = Assumptions(cash_buffer_mode="months", inflation=inflation)
        fi = project(simple_plan(cash_flows=flows, assumptions=assumptions)).fire.fi_dates[0]
        assert fi is not None
        return fi

    # Every euro is nominal here, so inflation changes nothing that FI depends on.
    assert fi_at(0.04) == fi_at(0.0)


def test_projected_flow_totals_are_recorded_monthly() -> None:
    """flow_totals records each month's income/expense/contribution/housing totals.

    This is View 6's data: run-independent, including the housing outflow (mortgage
    payment + VvE).
    """
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="salary",
            amount_monthly=Decimal(3000),
            kind=CashFlowKind.INCOME,
            inflation_linked=False,
        ),
        CashFlow(
            id=2,
            household_id=1,
            label="rent",
            amount_monthly=Decimal(1200),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        ),
        CashFlow(
            id=3,
            household_id=1,
            label="DCA",
            amount_monthly=Decimal(500),
            kind=CashFlowKind.CONTRIBUTION,
            target_account_id=2,
            inflation_linked=False,
        ),
    ]
    p = project(simple_plan(cash_flows=flows, assumptions=NO_SWEEP))
    for key in ("income", "expenses", "contributions", "housing"):
        assert len(p.flow_totals[key]) == len(p.months)
        assert p.flow_totals[key][0] == 0.0  # index 0 is the opening position
    assert p.flow_totals["income"][1] == pytest.approx(3000.0)
    assert p.flow_totals["expenses"][12] == pytest.approx(1200.0)
    assert p.flow_totals["contributions"][5] == pytest.approx(500.0)
    assert p.flow_totals["housing"][5] == 0.0


def test_housing_flow_totals_carry_the_mortgage_payment_and_vve() -> None:
    """flow_totals['housing'] is zero before a purchase and includes payment + VvE after."""
    m = Milestone(
        id=1,
        household_id=1,
        label="buy",
        params=BuyProperty(
            price=Decimal(360000),
            mortgage=Decimal(300000),
            annual_rate=Decimal("0.035"),
            vve_monthly=Decimal(200),
        ),
        on_date=date(2026, 6, 1),
    )
    p = project(simple_plan(milestones=[m], assumptions=NO_SWEEP))
    before = p.flow_totals["housing"][month_of := 5]  # 2026-05, pre-purchase
    after = p.flow_totals["housing"][month_of + 2]  # 2026-07, owned
    assert before == 0.0
    assert after > 1300.0  # annuity on 300k at 3.5% is ~1347, plus 200 VvE


def test_investment_income_captures_monthly_portfolio_gains() -> None:
    """The passive-income series accumulates the euro gain on liquid investments."""
    p = project(simple_plan(assumptions=NO_SWEEP))
    assert p.investment_income.shape == p.net_worth.shape
    assert p.investment_income[0, 0] == 0.0  # the opening index has no gain
    assert p.investment_income[0, 1:].sum() > 0.0  # a 6% equity portfolio earns something


def test_net_swr_sits_below_gross_when_box3_taxes_the_portfolio() -> None:
    """A Box 3 investment portfolio drags the net SWR below the gross assumption."""
    p = project(simple_plan(assumptions=NO_SWEEP))
    assert 0.0 < p.fire.net_swr < 0.04


def test_net_swr_equals_gross_without_a_box3_portfolio() -> None:
    """With no Box 3 investments there is no drag, so net SWR is the gross assumption."""
    cash_only = [
        Account(
            id=1,
            household_id=1,
            owner_person_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(10000),
            return_assumption=0.0,
        )
    ]
    p = project(simple_plan(accounts=cash_only, assumptions=NO_SWEEP))
    assert p.fire.net_swr == pytest.approx(0.04)


class _RealizationRegime(NLTaxRegime):
    """A stand-in for a realization-tax country (AT), reusing the Dutch arithmetic.

    The point is the treatment *sets*, not the figures: the ordinary investment
    wrapper is taxed on the way out (KESt on the realized gain), and is still exactly
    where surplus cash belongs. Under NL those two facts never co-occur.
    """

    def withdrawal_taxed_treatments(self) -> frozenset[str]:
        return frozenset({"nl.box3_investment"})

    def sweep_excluded_treatments(self) -> frozenset[str]:
        return frozenset()

    def withdrawal_tax(
        self,
        amount: np.ndarray,
        *,
        treatment: str,
        realized_gain: np.ndarray,
        owner_person_id: int | None,
        year: int,
        cfg: NLTaxConfig,
    ) -> np.ndarray:
        """27.5% of the gain, not of the gross — the whole point of a realization tax."""
        del amount, treatment, owner_person_id, year, cfg
        return np.maximum(0.0, realized_gain) * 0.275


def test_a_wrapper_taxed_on_withdrawal_can_still_be_a_sweep_destination() -> None:
    """Being taxed on the way out must not disqualify a wrapper from receiving cash.

    The engine used one set for both "withdrawal_tax may charge here" and "never sweep
    into this". Under NL they coincide (only the lijfrente). Under a realization tax
    every ordinary investment account is taxed on the way out, so the two must be
    separate sets or the sweep never invests and the portfolio sits in cash forever.
    """
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="salary",
            amount_monthly=Decimal(5000),
            kind=CashFlowKind.INCOME,
            inflation_linked=False,
        )
    ]
    accounts = [
        Account(
            id=1,
            household_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(10000),
        ),
        Account(
            id=2,
            household_id=1,
            name="Equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.box3_investment",
            manual_value=Decimal(100000),
            cost_basis=Decimal(100000),
        ),
    ]
    projection = project(
        simple_plan(cash_flows=flows, accounts=accounts), regime=_RealizationRegime()
    )
    invested = projection.components["liquid_investments"][0]
    assert invested[-1] > invested[0], "surplus cash was never swept into the taxed wrapper"


def test_a_sale_realizes_only_the_embedded_gain_not_the_gross() -> None:
    """A sale consumes cost basis pro rata, so only the profit part is a realized gain.

    The account opens at 100k with a 50k basis, so exactly half of every euro taken out
    is gain. That proportion is the moving-average method (Austria's gleitender
    Durchschnittspreis), and it is what a realization tax must be charged on — taxing the
    gross would tax the return of capital.
    """
    seen: list[tuple[np.ndarray, np.ndarray]] = []

    class _Recording(_RealizationRegime):
        def withdrawal_tax(
            self,
            amount: np.ndarray,
            *,
            treatment: str,
            realized_gain: np.ndarray,
            owner_person_id: int | None,
            year: int,
            cfg: NLTaxConfig,
        ) -> np.ndarray:
            """Record what the engine handed over, and charge nothing."""
            seen.append((amount.copy(), realized_gain.copy()))
            return np.zeros_like(amount)

    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="spending",
            amount_monthly=Decimal(4000),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        )
    ]
    accounts = [
        Account(
            id=1,
            household_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(0),
        ),
        Account(
            id=2,
            household_id=1,
            name="Equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.box3_investment",
            manual_value=Decimal(100000),
            cost_basis=Decimal(50000),
        ),
    ]
    # No income, so the buffer is short every month and the sweep must sell to fund it.
    project(
        simple_plan(cash_flows=flows, accounts=accounts, assumptions=Assumptions(inflation=0.0)),
        regime=_Recording(),
    )

    assert seen, "the sweep never sold, so the gain was never exercised"
    withdrawn, gain = seen[0]
    # Half the position is gain at the first sale, before any growth moves the ratio.
    np.testing.assert_allclose(gain[0], withdrawn[0] * 0.5, rtol=1e-6)
    # Never more gain than was taken out, in any sale.
    for w, g in seen:
        assert np.all(g <= w + 1e-9)
        assert np.all(g >= -1e-9)


def test_a_later_loss_reduces_the_tax_on_an_earlier_gain_in_the_same_year() -> None:
    """Within-year loss offset: the charge is computed on running totals, not per sale.

    A regime whose charge is linear in the gain sees no difference. One that floors
    losses at zero — every realization tax — must not tax a March gain that a November
    loss has already wiped out, because that is what a depot bank's automatic
    Verlustausgleich does.
    """
    charges: list[np.ndarray] = []
    gains_seen: list[np.ndarray] = []

    class _Recording(_RealizationRegime):
        def withdrawal_tax(
            self,
            amount: np.ndarray,
            *,
            treatment: str,
            realized_gain: np.ndarray,
            owner_person_id: int | None,
            year: int,
            cfg: NLTaxConfig,
        ) -> np.ndarray:
            """Charge 27.5% of the running net gain, flooring a net loss at zero."""
            gains_seen.append(realized_gain.copy())
            out = np.maximum(0.0, realized_gain) * 0.275
            charges.append(out.copy())
            return out

    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="spending",
            amount_monthly=Decimal(4000),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        )
    ]
    accounts = [
        Account(
            id=1,
            household_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(0),
        ),
        Account(
            id=2,
            household_id=1,
            name="Equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.box3_investment",
            manual_value=Decimal(500000),
            cost_basis=Decimal(250000),
        ),
    ]
    project(
        simple_plan(cash_flows=flows, accounts=accounts, assumptions=Assumptions(inflation=0.0)),
        regime=_Recording(),
    )

    assert gains_seen, "the sweep never sold"
    # The gain handed over accumulates within the year rather than resetting per sale.
    first_year = gains_seen[:11]
    assert all(float(b[0]) >= float(a[0]) - 1e-9 for a, b in pairwise(first_year)), (
        "the year-to-date realized gain went backwards without a loss to explain it"
    )


def test_income_from_a_distribution_yield_reaches_the_regime() -> None:
    """`distribution_yield` decomposes the return into income the regime can tax."""
    seen: list[dict[str, np.ndarray]] = []

    class _Recording(NLTaxRegime):
        def annual_investment_tax(self, s: YearState, cfg: NLTaxConfig) -> np.ndarray:
            """Record the income split, then defer to the real Dutch calculation."""
            seen.append({k: v.copy() for k, v in s.income_by_treatment.items()})
            return super().annual_investment_tax(s, cfg)

    accounts = [
        Account(
            id=1,
            household_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(10000),
        ),
        Account(
            id=2,
            household_id=1,
            name="Equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.box3_investment",
            manual_value=Decimal(100000),
            cost_basis=Decimal(100000),
            distribution_yield=0.02,
        ),
    ]
    project(simple_plan(accounts=accounts, assumptions=NO_SWEEP), regime=_Recording())

    assert seen, "no tax year was closed"
    first = seen[0]["nl.box3_investment"][0]
    # 2% of a 100k position over a year, accrued monthly on a flat balance.
    assert first == pytest.approx(2000.0, rel=0.02)


def test_a_zero_distribution_yield_reports_no_income_at_all() -> None:
    """The default must leave every existing projection exactly as it was."""
    seen: list[dict[str, np.ndarray]] = []

    class _Recording(NLTaxRegime):
        def annual_investment_tax(self, s: YearState, cfg: NLTaxConfig) -> np.ndarray:
            """Record the income split, then defer to the real Dutch calculation."""
            seen.append({k: v.copy() for k, v in s.income_by_treatment.items()})
            return super().annual_investment_tax(s, cfg)

    project(simple_plan(assumptions=NO_SWEEP), regime=_Recording())
    assert seen
    assert seen[0] == {}


def test_two_withdrawal_taxed_treatments_keep_separate_loss_pools() -> None:
    """Each taxed treatment nets its own gains; they must not share one accumulator.

    Austria is explicit that the 25% and 27.5% buckets do not pool for loss relief, and
    the same applies to any two treatments a regime taxes differently. Sharing one
    running total also double-counts: every treatment would compute tax on the combined
    pool while subtracting only what it had itself charged.
    """
    seen: dict[str, list[np.ndarray]] = {"a": [], "b": []}

    class _TwoPools(NLTaxRegime):
        def withdrawal_taxed_treatments(self) -> frozenset[str]:
            return frozenset({"nl.box3_investment", "nl.box1_pension"})

        def sweep_excluded_treatments(self) -> frozenset[str]:
            return frozenset()

        def withdrawal_tax(
            self,
            amount: np.ndarray,
            *,
            treatment: str,
            realized_gain: np.ndarray,
            owner_person_id: int | None,
            year: int,
            cfg: NLTaxConfig,
        ) -> np.ndarray:
            """Record the running gain each pool is shown, and charge nothing."""
            key = "a" if treatment == "nl.box3_investment" else "b"
            seen[key].append(realized_gain.copy())
            return np.zeros_like(amount)

    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="spending",
            amount_monthly=Decimal(6000),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        )
    ]
    accounts = [
        Account(
            id=1,
            household_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(0),
        ),
        Account(
            id=2,
            household_id=1,
            name="Equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.box3_investment",
            manual_value=Decimal(300000),
            cost_basis=Decimal(150000),
        ),
        Account(
            id=3,
            household_id=1,
            name="Lijfrente",
            kind=AccountKind.PENSION,
            tax_treatment="nl.box1_pension",
            manual_value=Decimal(300000),
            cost_basis=Decimal(300000),
            liquid_from=date(2026, 1, 1),
        ),
    ]
    project(
        simple_plan(cash_flows=flows, accounts=accounts, assumptions=Assumptions(inflation=0.0)),
        regime=_TwoPools(),
    )

    assert seen["a"], "the equity treatment was never sold from"
    assert seen["b"], "the pension treatment was never sold from"
    # The pension was bought at its own value, so it carries no gain at all. If the two
    # treatments shared one accumulator, the equity's gain would leak into its pool.
    assert float(seen["b"][0][0]) == pytest.approx(0.0, abs=1e-6), (
        "a treatment with no embedded gain was charged on another treatment's gain"
    )


def test_year_state_splits_owned_from_joint_holdings() -> None:
    """The engine states ownership per person and applies no tax share of its own.

    A joint account appears whole in every person's `joint` map rather than pre-divided:
    what fraction falls inside a citizenship's net follows from filing status, which is
    that country's rule and not something engine.py may know (invariant #1).

    The maps are keyed by `overlay_treatment`, not by the residence treatment, because a
    `CitizenshipOverlay` is their only reader and may never interpret an `nl.*` key. An
    account with no overlay classification is carried under `None` rather than dropped.
    """
    captured: list[YearState] = []

    class _Recorder(NLTaxRegime):
        def annual_investment_tax(self, s: YearState, cfg: NLTaxConfig) -> np.ndarray:
            captured.append(s)
            return super().annual_investment_tax(s, cfg)

    plan = PlanInput(
        household=Household(id=1, name="T", tax_country="NL", fiscal_partners=True),
        people=[
            Person(id=1, household_id=1, name="A", birth_date=date(1985, 1, 1)),
            Person(id=2, household_id=1, name="B", birth_date=date(1987, 1, 1)),
        ],
        accounts=[
            Account(
                id=1,
                household_id=1,
                name="Joint cash",
                kind=AccountKind.CASH,
                tax_treatment="nl.box3_bank",
                manual_value=Decimal(20_000),
            ),
            Account(
                id=2,
                household_id=1,
                name="A's brokerage",
                kind=AccountKind.EQUITY,
                tax_treatment="nl.box3_investment",
                overlay_treatment="us.non_pfic",
                manual_value=Decimal(100_000),
                owner_person_id=1,
            ),
        ],
        cash_flows=[],
        milestones=[],
        start=TODAY,
        # Sweep off: with no expenses the buffer target is zero, so the sweep would move
        # every joint euro into the owned brokerage and there would be nothing joint left
        # to assert on.
        assumptions=Assumptions(inflation=0.0, cash_buffer_mode="off"),
    )

    project(plan, regime=_Recorder())

    state = captured[0]
    assert state.by_person[1].owned.balances["us.non_pfic"] > 0
    # B owns nothing outright, but shares the joint account whole.
    assert "us.non_pfic" not in state.by_person[2].owned.balances
    # The joint cash carries no overlay classification, so it lands under None.
    assert state.by_person[1].joint.balances[None] > 0
    assert state.by_person[2].joint.balances[None] == pytest.approx(
        state.by_person[1].joint.balances[None]
    )


def test_earned_income_is_attributed_to_the_person_who_earns_it() -> None:
    """A citizenship overlay taxes one person's income, so the engine must attribute it."""
    captured: list[YearState] = []

    class _Recorder(NLTaxRegime):
        def annual_investment_tax(self, s: YearState, cfg: NLTaxConfig) -> np.ndarray:
            captured.append(s)
            return super().annual_investment_tax(s, cfg)

    plan = PlanInput(
        household=Household(id=1, name="T", tax_country="NL", fiscal_partners=True),
        people=[
            Person(id=1, household_id=1, name="A", birth_date=date(1985, 1, 1)),
            Person(id=2, household_id=1, name="B", birth_date=date(1987, 1, 1)),
        ],
        accounts=[
            Account(
                id=1,
                household_id=1,
                name="Cash",
                kind=AccountKind.CASH,
                tax_treatment="nl.box3_bank",
                manual_value=Decimal(10_000),
            )
        ],
        cash_flows=[
            CashFlow(
                id=1,
                household_id=1,
                label="A's salary",
                amount_monthly=Decimal(4_000),
                kind=CashFlowKind.INCOME,
                owner_person_id=1,
                inflation_linked=False,
            )
        ],
        milestones=[],
        start=TODAY,
        assumptions=Assumptions(inflation=0.0),
    )

    project(plan, regime=_Recorder())

    state = captured[0]
    assert state.by_person[1].earned_income == pytest.approx(48_000.0)
    assert state.by_person[2].earned_income == pytest.approx(0.0)


def test_two_owners_of_one_treatment_keep_separate_loss_pools() -> None:
    """A within-year loss offset is per taxpayer, never pooled across a couple.

    Austria's Verlustausgleich is explicitly per Steuerpflichtiger, and every realization
    tax works the same way: one partner's loss cannot reduce the tax on the other's gain.
    Before the running totals were keyed by owner they were keyed by treatment alone, so
    two people holding the same treatment were charged on one combined pool.
    """
    seen: list[tuple[int | None, np.ndarray]] = []

    class _Recording(_RealizationRegime):
        def withdrawal_tax(
            self,
            amount: np.ndarray,
            *,
            treatment: str,
            realized_gain: np.ndarray,
            owner_person_id: int | None,
            year: int,
            cfg: NLTaxConfig,
        ) -> np.ndarray:
            seen.append((owner_person_id, realized_gain.copy()))
            return np.maximum(0.0, realized_gain) * 0.275

    accounts = [
        Account(
            id=1,
            household_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(0),
        ),
        # One holds a large embedded gain, the other is at cost. Pooling would let the
        # second person's basis dilute the first person's taxable gain.
        Account(
            id=2,
            household_id=1,
            name="A's equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.box3_investment",
            manual_value=Decimal(300000),
            cost_basis=Decimal(100000),
            owner_person_id=1,
        ),
        Account(
            id=3,
            household_id=1,
            name="B's equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.box3_investment",
            manual_value=Decimal(300000),
            cost_basis=Decimal(300000),
            owner_person_id=2,
        ),
    ]
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="spending",
            amount_monthly=Decimal(4000),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=False,
        )
    ]

    project(
        simple_plan(cash_flows=flows, accounts=accounts, assumptions=Assumptions(inflation=0.0)),
        regime=_Recording(),
    )

    assert seen, "the sweep never sold"
    owners = {owner for owner, _ in seen}
    assert owners == {1, 2}, f"both owners must be charged separately, saw {owners}"
    # Each owner's running gain is its own series: B sells at cost and realizes nothing,
    # while A realizes a gain. A pooled total would have shown B a share of A's gain.
    b_gains = [float(g[0]) for owner, g in seen if owner == 2]
    assert all(g == pytest.approx(0.0) for g in b_gains), (
        f"B sold only at cost yet was handed a gain: {b_gains}"
    )


def test_a_us_person_is_now_charged_and_a_household_without_one_is_not() -> None:
    """The pin phase 2 set, flipped: the overlay is registered and it moves the numbers.

    Both halves matter. A US person must now pay more than an otherwise identical non-US
    person — the salary here is above the section 911 exclusion, so a real US charge
    survives it — and the household without one must still project exactly what it
    projected before any of this existed. `tests/golden/baseline.json` guards that second
    half for the example household; this guards it for one with investments and a salary.
    """

    def plan_for(*, us: bool) -> PlanInput:
        return PlanInput(
            household=Household(id=1, name="T", tax_country="NL", fiscal_partners=False),
            people=[
                Person(
                    id=1,
                    household_id=1,
                    name="A",
                    birth_date=date(1985, 1, 1),
                    us_person=us,
                    us_filing_status="single" if us else None,
                )
            ],
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
                    name="Schwab",
                    kind=AccountKind.EQUITY,
                    tax_treatment="nl.box3_investment",
                    overlay_treatment="us.non_pfic",
                    manual_value=Decimal(300_000),
                    cost_basis=Decimal(150_000),
                    owner_person_id=1,
                ),
            ],
            cash_flows=[
                CashFlow(
                    id=1,
                    household_id=1,
                    label="A's salary",
                    amount_monthly=Decimal(20_000),
                    kind=CashFlowKind.INCOME,
                    owner_person_id=1,
                    inflation_linked=False,
                )
            ],
            milestones=[],
            start=TODAY,
            assumptions=Assumptions(inflation=0.0),
        )

    plain = project(plan_for(us=False))
    us_person = project(plan_for(us=True))

    assert us_person.tax_paid["investment_tax"].sum() > plain.tax_paid["investment_tax"].sum()
    assert us_person.net_worth[0][-1] < plain.net_worth[0][-1]


def test_an_overlays_year_is_charged_once_and_its_carry_threaded() -> None:
    """Each tax year reaches the overlay once, holding the carry the year before returned.

    An overlay's carry is the only cross-year state in the design — a US person's § 904
    credit bank and § 1296 loss pool. Dropping it between years, or advancing it twice in
    one, would age the ten-year carryforward wrongly and miscount every PFIC mark.
    """
    charged_years: list[int] = []
    carried: list[int | None] = []

    @dataclass
    class _CountingOverlay:
        # "NL", not "US": `HouseholdTax` resolves the overlay's own config by this key, and
        # this test must not depend on some other test having imported `vuurtoren.tax.us`
        # to register it. The stub reads nothing off the config but its year.
        citizenship: str = "NL"

        def annual_tax(
            self,
            s: PersonSlice,
            cfg: TaxConfigBase,
            *,
            residence_tax: np.ndarray,
            carry: int | None,
        ) -> tuple[np.ndarray, int]:
            charged_years.append(cfg.year)
            carried.append(carry)
            return np.zeros_like(residence_tax), cfg.year

        def withdrawal_tax(
            self,
            amount: np.ndarray,
            *,
            treatment: str,
            realized_gain: np.ndarray,
            cfg: object,
        ) -> np.ndarray:
            return np.zeros_like(realized_gain)

        def valid_treatments(self) -> frozenset[str]:
            return frozenset()

        def validate_accounts(
            self,
            accounts: object,
            *,
            person: object,
        ) -> None:
            return

    person = Person(id=1, household_id=1, name="A", birth_date=date(1985, 1, 1), us_person=True)
    plan = PlanInput(
        household=Household(id=1, name="T", tax_country="NL", fiscal_partners=False),
        people=[person],
        accounts=[
            Account(
                id=1,
                household_id=1,
                name="Cash",
                kind=AccountKind.CASH,
                tax_treatment="nl.box3_bank",
                manual_value=Decimal(200_000),
                owner_person_id=1,
            )
        ],
        cash_flows=[],
        milestones=[],
        start=TODAY,
        assumptions=Assumptions(inflation=0.0),
    )

    with mock.patch.object(
        vuurtoren.engine, "overlays_for", return_value=((person, _CountingOverlay()),)
    ):
        project(plan)

    assert charged_years == sorted(set(charged_years)), (
        f"a tax year was charged more than once: {charged_years}"
    )
    assert carried == [None, *charged_years[:-1]], "each year must get the last one's carry"


def test_a_us_person_still_owes_the_united_states_after_emigrating() -> None:
    """`ChangeTaxResidence` swaps the residence regime; it must not drop the overlays.

    Citizenship-based taxation is the one thing moving country does not end, so a
    projection where a US person emigrates and stops owing the United States anything is
    wrong in the most basic possible way. Austria charges nothing annual, so after the
    move the whole annual charge is the overlay's — if it were dropped there would be
    none at all, which is exactly what the bare-regime reassignment used to produce.
    """
    plan = PlanInput(
        household=Household(id=1, name="T", tax_country="NL", fiscal_partners=False),
        people=[
            Person(
                id=1,
                household_id=1,
                name="A",
                birth_date=date(1985, 1, 1),
                us_person=True,
                us_filing_status="single",
            )
        ],
        accounts=[
            Account(
                id=1,
                household_id=1,
                name="Cash",
                kind=AccountKind.CASH,
                tax_treatment="nl.box3_bank",
                manual_value=Decimal(50_000),
                owner_person_id=1,
            ),
            Account(
                id=2,
                household_id=1,
                name="Schwab",
                kind=AccountKind.EQUITY,
                tax_treatment="nl.box3_investment",
                overlay_treatment="us.non_pfic",
                # Big enough that the dividends clear the standard deduction and the 0 %
                # preferential band: a smaller pot owes the United States nothing even
                # when the overlay is working perfectly, so it could not tell the two
                # apart.
                manual_value=Decimal(5_000_000),
                cost_basis=Decimal(2_500_000),
                owner_person_id=1,
                distribution_yield=0.04,
            ),
        ],
        cash_flows=[],
        milestones=[
            Milestone(
                id=1,
                household_id=1,
                label="Move to Vienna",
                on_date=date(TODAY.year + 2, 1, 1),
                params=ChangeTaxResidence(country="AT", retag={1: "at.bank", 2: "at.investment"}),
            )
        ],
        start=TODAY,
        assumptions=Assumptions(inflation=0.0),
    )
    stateless = replace(
        plan, people=[p.model_copy(update={"us_person": False}) for p in plan.people]
    )

    charged = project(plan).tax_paid["investment_tax"][0]
    austria_alone = project(stateless).tax_paid["investment_tax"][0]

    # The first Austrian year, before the two households' balances drift apart.
    assert charged[2] > austria_alone[2], (
        "the move charges only Austria's tax — the citizenship overlay was dropped"
    )


def test_an_unelected_pfic_stops_the_projection_before_it_starts() -> None:
    """The refusal is wired into `project`, and fires up front rather than mid-horizon."""
    plan = PlanInput(
        household=Household(id=1, name="T", tax_country="NL", fiscal_partners=False),
        people=[
            Person(
                id=1,
                household_id=1,
                name="A",
                birth_date=date(1985, 1, 1),
                us_person=True,
                us_filing_status="single",
            )
        ],
        accounts=[
            Account(
                id=1,
                household_id=1,
                name="UCITS ETF",
                kind=AccountKind.EQUITY,
                tax_treatment="nl.box3_investment",
                overlay_treatment="us.pfic_none",
                manual_value=Decimal(100_000),
                owner_person_id=1,
            )
        ],
        cash_flows=[],
        milestones=[],
        start=TODAY,
        assumptions=Assumptions(inflation=0.0),
    )

    with pytest.raises(ValueError, match="UCITS ETF"):
        project(plan)


def test_selling_costs_a_us_person_tax_the_netherlands_does_not_charge() -> None:
    """Realization is the whole shape of US investment tax, and Box 3 never sees it.

    A decumulating household with no income at all: the cash sweep sells from the
    brokerage every month to fund spending, realizing gain against a low cost basis. The
    Dutch charge is identical either way — Box 3 taxes the holding, not the sale — so any
    difference between the two projections is the US charge on realization, which is what
    `PersonSlice.realized_gains` carries to the overlay.
    """

    def plan_for(*, us: bool) -> PlanInput:
        return PlanInput(
            household=Household(id=1, name="T", tax_country="NL", fiscal_partners=False),
            people=[
                Person(
                    id=1,
                    household_id=1,
                    name="A",
                    birth_date=date(1960, 1, 1),
                    us_person=us,
                    us_filing_status="single" if us else None,
                )
            ],
            accounts=[
                Account(
                    id=1,
                    household_id=1,
                    name="Cash",
                    kind=AccountKind.CASH,
                    tax_treatment="nl.box3_bank",
                    manual_value=Decimal(10_000),
                    owner_person_id=1,
                ),
                Account(
                    id=2,
                    household_id=1,
                    name="Schwab",
                    kind=AccountKind.EQUITY,
                    tax_treatment="nl.box3_investment",
                    overlay_treatment="us.non_pfic",
                    manual_value=Decimal(2_000_000),
                    cost_basis=Decimal(200_000),
                    owner_person_id=1,
                ),
            ],
            cash_flows=[
                CashFlow(
                    id=1,
                    household_id=1,
                    label="Living",
                    amount_monthly=Decimal(12_000),
                    kind=CashFlowKind.EXPENSE,
                    inflation_linked=False,
                )
            ],
            milestones=[],
            start=TODAY,
            assumptions=Assumptions(inflation=0.0),
        )

    plain = project(plan_for(us=False))
    us_person = project(plan_for(us=True))

    assert us_person.net_worth[0][-1] < plain.net_worth[0][-1], (
        "a US person selling into a Dutch retirement should end up poorer than a "
        "non-US person doing exactly the same thing"
    )
