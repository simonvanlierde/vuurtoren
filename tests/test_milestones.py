"""The deferred milestone types.

Age-based timing, gift exemption, VvE and the AOW-derived pension unlock.
"""

from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from test_engine import TODAY, simple_plan
from vuurtoren.domain import (
    Account,
    AccountKind,
    BuyProperty,
    CashFlow,
    CashFlowKind,
    ContributionChange,
    ExpenseChange,
    ExtraRepayment,
    IncomeChange,
    LumpSumIn,
    Milestone,
    Person,
    Retire,
    SellProperty,
)
from vuurtoren.engine import Assumptions, PlanInput, Projection, project

FLAT = Assumptions(cash_buffer_mode="off", inflation=0.0)


def flat_cash_plan(**overrides: object) -> PlanInput:
    """simple_plan with zero-return accounts and no inflation.

    Every euro of movement in the cash history is then attributable to the
    mechanic under test.
    """
    accounts = [
        Account(
            id=1,
            household_id=1,
            owner_person_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.none",
            manual_value=Decimal(100000),
            return_assumption=0.0,
        ),
        Account(
            id=2,
            household_id=1,
            owner_person_id=1,
            name="Equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.none",
            manual_value=Decimal(50000),
            return_assumption=0.0,
        ),
    ]
    base: dict[str, object] = {"accounts": accounts, "assumptions": FLAT}
    return simple_plan(**(base | overrides))


def month_index(when: date) -> int:
    """Index into the recorded histories (index 0 is the opening position)."""
    return (when.year - TODAY.year) * 12 + (when.month - TODAY.month) + 1


def cash_delta(p: Projection, when: date) -> float:
    """Cash balance change from the month before `when` to `when`."""
    i = month_index(when)
    return float(p.components["cash"][0, i] - p.components["cash"][0, i - 1])


def income(
    amount: str, *, flow_id: int = 1, owner: int | None = None, linked: bool = False
) -> CashFlow:
    """Build an INCOME CashFlow of `amount` per month."""
    return CashFlow(
        id=flow_id,
        household_id=1,
        label=f"income {flow_id}",
        amount_monthly=Decimal(amount),
        kind=CashFlowKind.INCOME,
        owner_person_id=owner,
        inflation_linked=linked,
    )


def expense(amount: str, *, flow_id: int = 1, linked: bool = False) -> CashFlow:
    """Build an EXPENSE CashFlow of `amount` per month."""
    return CashFlow(
        id=flow_id,
        household_id=1,
        label=f"expense {flow_id}",
        amount_monthly=Decimal(amount),
        kind=CashFlowKind.EXPENSE,
        inflation_linked=linked,
    )


# --- age-based timing ---


def test_an_age_based_milestone_fires_in_the_birthday_month() -> None:
    """An age-based milestone fires the same month as the equivalent on_date milestone.

    Age 40 for a person born 1990-01-01 is 2030-01.
    """
    params = LumpSumIn(amount=Decimal(50000))
    by_age = Milestone(
        id=1, household_id=1, label="gift", params=params, age_person_id=1, age_years=40
    )
    by_date = Milestone(
        id=1, household_id=1, label="gift", params=params, on_date=date(2030, 1, 15)
    )
    a = project(flat_cash_plan(milestones=[by_age]))
    b = project(flat_cash_plan(milestones=[by_date]))
    assert np.array_equal(a.net_worth, b.net_worth)
    assert cash_delta(a, date(2030, 1, 1)) == pytest.approx(50000.0)


def test_an_age_based_milestone_with_an_unknown_person_fails_loudly() -> None:
    """An age_person_id with no matching person raises rather than silently never firing."""
    m = Milestone(
        id=1,
        household_id=1,
        label="gift",
        params=LumpSumIn(amount=Decimal(1)),
        age_person_id=99,
        age_years=34,
    )
    with pytest.raises(ValueError, match="99"):
        project(flat_cash_plan(milestones=[m]))


# --- income / expense / contribution changes ---


def test_income_change_applies_from_the_month_after_it_fires() -> None:
    """An IncomeChange milestone's new amount applies from the month after it fires."""
    flows = [income("3000")]
    m = Milestone(
        id=1,
        household_id=1,
        label="new job",
        params=IncomeChange(cash_flow_id=1, new_amount_monthly=Decimal(1000)),
        on_date=date(2026, 6, 15),
    )
    p = project(flat_cash_plan(cash_flows=flows, milestones=[m]))
    # The change fires in step 4 of 2026-06, after that month's income landed in step 1.
    assert cash_delta(p, date(2026, 6, 1)) == pytest.approx(3000.0)
    assert cash_delta(p, date(2026, 7, 1)) == pytest.approx(1000.0)


def test_a_changed_amount_is_quoted_in_euros_of_the_change_month() -> None:
    """After a change, an inflation-linked flow re-bases and inflates from the change month.

    Not from the projection start — the milestone's author typed a figure in the
    money of that day.
    """
    flows = [expense("1000", linked=True)]
    m = Milestone(
        id=1,
        household_id=1,
        label="rent reset",
        params=ExpenseChange(cash_flow_id=1, new_amount_monthly=Decimal(1000)),
        on_date=date(2031, 1, 15),
    )
    p = project(
        flat_cash_plan(
            cash_flows=flows,
            milestones=[m],
            assumptions=Assumptions(cash_buffer_mode="off", inflation=0.02),
        )
    )
    # 2031-02 is one month past the change: ~1000 * 1.02^(1/12), not ~1000 * 1.02^5.
    assert cash_delta(p, date(2031, 2, 1)) == pytest.approx(-1000 * 1.02 ** (1 / 12), abs=0.05)


def test_contribution_change_redirects_the_new_amount() -> None:
    """A ContributionChange milestone redirects the flow's new amount from the month it fires."""
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            label="DCA",
            amount_monthly=Decimal(500),
            kind=CashFlowKind.CONTRIBUTION,
            target_account_id=2,
            inflation_linked=False,
        )
    ]
    m = Milestone(
        id=1,
        household_id=1,
        label="save less",
        params=ContributionChange(cash_flow_id=1, new_amount_monthly=Decimal(200)),
        on_date=date(2026, 6, 1),
    )
    p = project(flat_cash_plan(cash_flows=flows, milestones=[m]))
    equity = p.components["liquid_investments"][0]
    assert float(equity[month_index(date(2026, 6, 1))] - equity[month_index(date(2026, 5, 1))]) == (
        pytest.approx(500.0)
    )
    assert float(equity[month_index(date(2026, 7, 1))] - equity[month_index(date(2026, 6, 1))]) == (
        pytest.approx(200.0)
    )


def test_a_flow_change_with_the_wrong_kind_fails_loudly() -> None:
    """An IncomeChange targeting an EXPENSE flow raises rather than silently misapplying."""
    flows = [expense("1000")]
    m = Milestone(
        id=1,
        household_id=1,
        label="wrong",
        params=IncomeChange(cash_flow_id=1, new_amount_monthly=Decimal(1)),
        on_date=date(2026, 6, 1),
    )
    with pytest.raises(ValueError, match="INCOME"):
        project(flat_cash_plan(cash_flows=flows, milestones=[m]))


def test_a_flow_change_with_an_unknown_flow_fails_loudly() -> None:
    """A cash_flow_id with no matching flow raises rather than silently no-opping."""
    m = Milestone(
        id=1,
        household_id=1,
        label="wrong",
        params=IncomeChange(cash_flow_id=42, new_amount_monthly=Decimal(1)),
        on_date=date(2026, 6, 1),
    )
    with pytest.raises(ValueError, match="42"):
        project(flat_cash_plan(milestones=[m]))


# --- retire ---


def test_retire_stops_that_persons_income_and_nobody_elses() -> None:
    """A retire milestone stops the person's own INCOME flows but not joint ones."""
    flows = [
        income("3000", flow_id=1, owner=1),
        income("1000", flow_id=2, owner=None),  # joint — must keep flowing
    ]
    m = Milestone(
        id=1,
        household_id=1,
        label="retire",
        params=Retire(person_id=1),
        on_date=date(2026, 6, 1),
    )
    p = project(flat_cash_plan(cash_flows=flows, milestones=[m]))
    assert cash_delta(p, date(2026, 6, 1)) == pytest.approx(4000.0)
    assert cash_delta(p, date(2026, 7, 1)) == pytest.approx(1000.0)


def test_retire_with_an_unknown_person_fails_loudly() -> None:
    """A Retire milestone with no matching person_id raises rather than silently no-opping."""
    m = Milestone(
        id=1,
        household_id=1,
        label="retire",
        params=Retire(person_id=7),
        on_date=date(2026, 6, 1),
    )
    with pytest.raises(ValueError, match="7"):
        project(flat_cash_plan(milestones=[m]))


# --- sell property ---


def _buy(when: date, *, vve: str = "0", gift: str = "0") -> Milestone:
    return Milestone(
        id=1,
        household_id=1,
        label="buy",
        params=BuyProperty(
            price=Decimal(360000),
            mortgage=Decimal(300000),
            annual_rate=Decimal("0.035"),
            vve_monthly=Decimal(vve),
            gift_used=Decimal(gift),
        ),
        on_date=when,
    )


def test_sell_property_returns_the_equity_to_cash_minus_costs() -> None:
    """A SellProperty milestone zeroes home_equity and debt, destroying only the sale costs."""
    sell = Milestone(
        id=2,
        household_id=1,
        label="sell",
        params=SellProperty(costs=Decimal(10000)),
        on_date=date(2030, 6, 1),
    )
    p = project(flat_cash_plan(milestones=[_buy(date(2026, 6, 1)), sell]))
    i = month_index(date(2030, 6, 1))
    assert float(p.components["home_equity"][0, i - 1]) > 0.0
    assert float(p.components["home_equity"][0, i]) == 0.0
    assert float(p.components["debt"][0, i]) == 0.0
    # No flows and zero returns: after the sale the cash line must be flat again
    # (the mortgage payment stopped with the mortgage).
    assert cash_delta(p, date(2030, 8, 1)) == pytest.approx(0.0)
    # The sale itself only destroys the selling costs, not equity: the sale fires
    # before the month's mortgage step, so nothing else leaves cash that month.
    nw_before = float(p.net_worth[0, i - 1])
    nw_after = float(p.net_worth[0, i])
    assert nw_before - nw_after == pytest.approx(10000.0, abs=5.0)


def test_sell_without_a_property_fails_loudly() -> None:
    """SellProperty with no property currently owned raises rather than silently no-opping."""
    sell = Milestone(
        id=1,
        household_id=1,
        label="sell",
        params=SellProperty(),
        on_date=date(2027, 1, 1),
    )
    with pytest.raises(ValueError, match=r"[Ss]ell"):
        project(flat_cash_plan(milestones=[sell]))


def test_a_second_purchase_after_a_sale_is_allowed() -> None:
    """Buying again after selling does not trip the single-mortgage guard."""
    sell = Milestone(
        id=2,
        household_id=1,
        label="sell",
        params=SellProperty(),
        on_date=date(2030, 6, 1),
    )
    rebuy = Milestone(
        id=3,
        household_id=1,
        label="buy again",
        params=BuyProperty(
            price=Decimal(300000), mortgage=Decimal(200000), annual_rate=Decimal("0.03")
        ),
        on_date=date(2032, 1, 1),
    )
    p = project(flat_cash_plan(milestones=[_buy(date(2026, 6, 1)), sell, rebuy]))
    assert float(p.components["home_equity"][0, -1]) > 0.0


# --- vve ---


def test_vve_is_charged_monthly_while_owned_and_stops_at_the_sale() -> None:
    """VvE is charged every month a property is owned and stops the month it is sold."""
    sell = Milestone(
        id=2,
        household_id=1,
        label="sell",
        params=SellProperty(),
        on_date=date(2028, 6, 1),
    )
    with_vve = project(flat_cash_plan(milestones=[_buy(date(2026, 6, 1), vve="200"), sell]))
    without = project(flat_cash_plan(milestones=[_buy(date(2026, 6, 1)), sell]))
    # Owned 2026-06 through 2028-05 inclusive = 24 months of 200 (zero inflation).
    gap = float(without.net_worth[0, -1] - with_vve.net_worth[0, -1])
    assert gap == pytest.approx(24 * 200.0, abs=1.0)
    # After the sale the two cash lines move in lockstep again.
    assert cash_delta(with_vve, date(2028, 8, 1)) == pytest.approx(
        cash_delta(without, date(2028, 8, 1))
    )


# --- gift exemption ---


def test_a_gift_at_purchase_reduces_the_cash_needed() -> None:
    """A tax-free gift used at purchase reduces the cash the household spends on the deposit."""
    with_gift = project(flat_cash_plan(milestones=[_buy(date(2026, 6, 1), gift="30000")]))
    without = project(flat_cash_plan(milestones=[_buy(date(2026, 6, 1))]))
    i = month_index(date(2026, 6, 1))
    assert float(
        with_gift.components["cash"][0, i] - without.components["cash"][0, i]
    ) == pytest.approx(30000.0)


def test_a_gift_above_the_onetime_exemption_fails_loudly() -> None:
    """A gift above the one-time exemption raises rather than silently understating tax."""
    # 2026 cap is 33,129 and the engine does not model schenkbelasting on the excess.
    with pytest.raises(ValueError, match="exemption"):
        project(flat_cash_plan(milestones=[_buy(date(2026, 6, 1), gift="40000")]))


def test_the_onetime_gift_exemption_is_single_use_per_person() -> None:
    """A second claimed onetime gift exemption for the same person raises."""
    first = Milestone(
        id=1,
        household_id=1,
        label="gift 1",
        params=LumpSumIn(amount=Decimal(33000), is_gift_exemption=True),
        on_date=date(2026, 6, 1),
    )
    second = Milestone(
        id=2,
        household_id=1,
        label="gift 2",
        params=LumpSumIn(amount=Decimal(33000), is_gift_exemption=True),
        on_date=date(2027, 6, 1),
    )
    assert project(flat_cash_plan(milestones=[first])).net_worth[0, -1] > 0
    with pytest.raises(ValueError, match="exemption"):
        project(flat_cash_plan(milestones=[first, second]))


def test_a_gift_outside_the_age_window_only_gets_the_annual_exemption() -> None:
    """Outside the 18-40 age window, a claimed onetime exemption falls back to the annual cap."""
    # Born 1990-01-01: 50 in 2040-06, past the 18-40 window, so 33,000 > the annual cap.
    m = Milestone(
        id=1,
        household_id=1,
        label="late gift",
        params=LumpSumIn(amount=Decimal(33000), is_gift_exemption=True),
        on_date=date(2040, 6, 1),
    )
    with pytest.raises(ValueError, match="exemption"):
        project(flat_cash_plan(milestones=[m]))


def test_the_onetime_exemption_ends_on_the_40th_birthday() -> None:
    """The Belastingdienst allows a gift on the 40th birthday itself, and none after it.

    Born 1990-01-01, so 40 from 2030-01-01: a June 2030 gift is still "age 40" in whole
    years, but past the window, so 30,000 exceeds the annual cap.
    """

    def gift_on(on_date: date) -> Milestone:
        return Milestone(
            id=1,
            household_id=1,
            label="gift",
            params=LumpSumIn(amount=Decimal(30000), is_gift_exemption=True),
            on_date=on_date,
        )

    project(flat_cash_plan(milestones=[gift_on(date(2030, 1, 1))]))
    with pytest.raises(ValueError, match="exemption"):
        project(flat_cash_plan(milestones=[gift_on(date(2030, 6, 1))]))


def test_a_distant_gift_is_measured_against_an_indexed_exemption() -> None:
    """A 2045 gift meets a 2045 exemption, not one still quoted in 2026 euros.

    The December tax step indexed its allowances and every other call site did not, so a
    gift decades out failed against a cap inflation had long overtaken. 33,129 in 2026
    euros is 48,262 by 2045 at 2%, which a 40,000 gift is comfortably inside.
    """
    m = Milestone(
        id=1,
        household_id=1,
        label="gift",
        params=LumpSumIn(amount=Decimal(40000), is_gift_exemption=True),
        on_date=date(2045, 6, 1),
    )
    # Born 2010, so 35 in 2045 and inside the 18-40 window the one-time exemption needs.
    people = [Person(id=1, household_id=1, name="A", birth_date=date(2010, 1, 1))]
    project(
        flat_cash_plan(
            people=people,
            milestones=[m],
            assumptions=Assumptions(cash_buffer_mode="off", inflation=0.02),
        )
    )
    # And the indexation is what saves it: turn it off and the same gift is over the cap.
    with pytest.raises(ValueError, match="exemption"):
        project(
            flat_cash_plan(
                people=people,
                milestones=[m],
                assumptions=Assumptions(
                    cash_buffer_mode="off", inflation=0.02, index_tax_allowances=False
                ),
            )
        )


# --- AOW-derived pension unlock ---


def _pension_plan(
    *, liquid_from: date | None, override: str | None = None, growth: int = 0
) -> PlanInput:
    """Build a plan with one PENSION account, its unlock timing set by the given fields."""
    accounts = [
        Account(
            id=1,
            household_id=1,
            owner_person_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.none",
            manual_value=Decimal(10000),
            return_assumption=0.0,
        ),
        Account(
            id=2,
            household_id=1,
            owner_person_id=1,
            name="Lijfrente",
            kind=AccountKind.PENSION,
            tax_treatment="nl.box1_pension",
            manual_value=Decimal(100000),
            return_assumption=0.0,
            liquid_from=liquid_from,
        ),
    ]
    people = [
        Person(
            id=1,
            household_id=1,
            name="A",
            birth_date=date(1990, 1, 1),
            pension_age_override=override,
        )
    ]
    return simple_plan(
        accounts=accounts,
        people=people,
        assumptions=Assumptions(
            cash_buffer_mode="off", inflation=0.0, state_pension_growth_months_per_decade=growth
        ),
    )


def _unlock_month(p: Projection) -> int:
    """First record index where the pension entered fire_usable.

    Zero returns, so the jump is exactly the pension balance. Records are labeled
    with the month they open, so the unlock date's own label is where the pension
    first counts.
    """
    usable = p.fire.fire_usable[0]
    jumps = np.flatnonzero(np.diff(usable) > 50000.0)
    assert len(jumps) == 1
    return int(jumps[0]) + 1


def label_index(when: date) -> int:
    """Index of the record labeled `when` (the position entering that month)."""
    return (when.year - TODAY.year) * 12 + (when.month - TODAY.month)


def test_a_pension_without_a_stored_unlock_derives_it_from_the_aow_schedule() -> None:
    """A pension with no stored liquid_from derives its unlock date from the AOW schedule."""
    # Born 1990-01-01, growth 0 -> AOW at 67y3m = 2057-04-01 (see test_regime).
    p = project(_pension_plan(liquid_from=None))
    assert _unlock_month(p) == label_index(date(2057, 4, 1))


def test_a_stored_liquid_from_wins_over_the_derived_date() -> None:
    """A stored liquid_from overrides the date the AOW schedule would otherwise derive."""
    p = project(_pension_plan(liquid_from=date(2040, 1, 1)))
    assert _unlock_month(p) == label_index(date(2040, 1, 1))


def test_a_pension_age_override_beats_the_schedule() -> None:
    """A person's pension_age_override beats both the AOW schedule and any stored date."""
    p = project(_pension_plan(liquid_from=None, override="70y"))
    assert _unlock_month(p) == label_index(date(2060, 1, 1))


def test_a_pension_age_override_parses_years_and_months() -> None:
    """A pension_age_override like '67y3m' parses both the years and months components."""
    p = project(_pension_plan(liquid_from=None, override="67y3m"))
    assert _unlock_month(p) == label_index(date(2057, 4, 1))


def test_a_malformed_pension_age_override_fails_loudly() -> None:
    """A pension_age_override that does not match the 'NNyNNm' format raises."""
    with pytest.raises(ValueError, match="pension_age_override"):
        project(_pension_plan(liquid_from=None, override="at 67"))


# --- review regressions: gift exemption, sale-year deduction, extra repayment ---


def test_a_gift_inside_the_annual_exemption_leaves_the_onetime_one_unused() -> None:
    """A small gift is covered by the annual exemption and needs no one-time claim.

    Marking the one-time exemption used on any gift refused a later, larger gift the
    recipient (30 in 2026) was still entitled to.
    """
    small = Milestone(
        id=1,
        household_id=1,
        label="small gift",
        params=LumpSumIn(amount=Decimal(5000), is_gift_exemption=True),
        on_date=date(2026, 6, 1),
    )
    large = Milestone(
        id=2,
        household_id=1,
        label="large gift",
        params=LumpSumIn(amount=Decimal(25000), is_gift_exemption=True),
        on_date=date(2028, 6, 1),
    )
    project(flat_cash_plan(milestones=[small, large]))


def _sell(when: date, milestone_id: int = 2) -> Milestone:
    return Milestone(
        id=milestone_id, household_id=1, label="sell", params=SellProperty(), on_date=when
    )


def test_the_year_of_sale_keeps_its_mortgage_interest_deduction() -> None:
    """Interest paid before the sale is deductible against a pro-rated forfait.

    Selling zeroed the home before December, so the year-of-sale deduction vanished.
    Sold 1 July 2030: six months of interest against half a year's forfait, so the 2030
    figure is about half of a full year's.
    """
    p = project(flat_cash_plan(milestones=[_buy(date(2026, 6, 1)), _sell(date(2030, 7, 1))]))
    adjustment = p.tax_paid["housing_adjustment"][0]
    full_year, sale_year = float(adjustment[3]), float(adjustment[4])
    assert full_year > 0.0
    assert 0.4 * full_year < sale_year < 0.6 * full_year
    assert float(adjustment[5]) == 0.0


def test_selling_stops_the_extra_repayment() -> None:
    """An extra repayment belongs to the mortgage it was paying off, not the next one."""
    extra = Milestone(
        id=3,
        household_id=1,
        label="aflossen",
        params=ExtraRepayment(monthly_amount=Decimal(500)),
        on_date=date(2027, 1, 1),
    )
    rebuy = Milestone(
        id=4,
        household_id=1,
        label="buy again",
        params=BuyProperty(
            price=Decimal(300000), mortgage=Decimal(200000), annual_rate=Decimal("0.03")
        ),
        on_date=date(2032, 1, 1),
    )
    base = [_buy(date(2026, 6, 1)), _sell(date(2030, 6, 1)), rebuy]
    with_extra = project(flat_cash_plan(milestones=[*base, extra]))
    without = project(flat_cash_plan(milestones=base))
    i = month_index(date(2040, 1, 1))
    assert float(with_extra.components["debt"][0, i]) == pytest.approx(
        float(without.components["debt"][0, i])
    )
