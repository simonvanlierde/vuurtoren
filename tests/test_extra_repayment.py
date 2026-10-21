"""Extra mortgage repayment — the aflossen half of aflossen-vs-beleggen."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np

from test_engine import simple_plan
from vuurtoren.domain import (
    Account,
    AccountKind,
    BuyProperty,
    CashFlow,
    CashFlowKind,
    ExtraRepayment,
    Household,
    Milestone,
    Person,
    Scenario,
    ScenarioOverrides,
)
from vuurtoren.engine import project
from vuurtoren.scenarios import apply_scenario

if TYPE_CHECKING:
    from vuurtoren.engine import PlanInput

BUY = date(2026, 2, 1)


def _plan(*, extra: str | None = None, from_date: date = date(2027, 1, 1)) -> PlanInput:
    """A household that buys a house, optionally repaying extra from `from_date`."""
    household = Household(id=1, name="T", fiscal_partners=False, life_expectancy_age=70)
    people = [Person(id=1, household_id=1, name="A", birth_date=date(1990, 1, 1))]
    accounts = [
        Account(
            id=1,
            household_id=1,
            owner_person_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(200_000),
            return_assumption=0.0,
        ),
    ]
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            owner_person_id=1,
            label="salary",
            amount_monthly=Decimal(6000),
            kind=CashFlowKind.INCOME,
            inflation_linked=True,
        ),
    ]
    milestones = [
        Milestone(
            id=1,
            household_id=1,
            label="buy",
            on_date=BUY,
            params=BuyProperty(
                price=Decimal(400_000),
                mortgage=Decimal(300_000),
                annual_rate=Decimal("0.04"),
                term_months=360,
            ),
        )
    ]
    if extra is not None:
        milestones.append(
            Milestone(
                id=2,
                household_id=1,
                label="aflossen",
                on_date=from_date,
                params=ExtraRepayment(monthly_amount=Decimal(extra)),
            )
        )
    return simple_plan(
        household=household,
        people=people,
        accounts=accounts,
        cash_flows=flows,
        milestones=milestones,
        start=date(2026, 1, 1),
    )


def _debt(proj: object) -> np.ndarray:
    """Run 0's debt component as a positive outstanding balance."""
    return -np.asarray(proj.components["debt"][0])  # ty: ignore[unresolved-attribute]


MID = (2040 - 2026) * 12
"""A month with the mortgage still live in both arms — the 30-year term runs to 2056,
and comparing at the horizon would find both at zero and prove nothing."""


def test_extra_repayment_shrinks_the_balance_faster() -> None:
    """The whole point: paying extra leaves less owed at every later month."""
    base = _debt(project(_plan()))
    extra = _debt(project(_plan(extra="500")))
    assert extra[MID] < base[MID]
    # And never the other way round, at any month at all.
    assert np.all(extra <= base + 1e-6)


def test_extra_repayment_clears_the_mortgage_early() -> None:
    """The term shortens rather than the monthly payment dropping.

    The annuity payment is untouched by an extra repayment, so the mortgage simply ends
    sooner instead of costing less each month.
    """
    base = _debt(project(_plan()))
    extra = _debt(project(_plan(extra="1000")))

    def repaid(d: np.ndarray) -> int:
        """First month at zero *after* the purchase — index 0 predates the mortgage."""
        after = d[MID:] <= 0.01
        return MID + int(np.argmax(after))

    assert repaid(extra) < repaid(base)


def test_extra_repayment_costs_the_cash_it_pays() -> None:
    """The money leaves the cash account while the mortgage is still being paid down.

    Measured a year in, not at the horizon: by then the interest saved outweighs the
    cash paid out, which is a different (and also true) claim — see the test below.
    """
    a_year_in = (2028 - 2026) * 12
    b_cash = np.asarray(project(_plan()).components["cash"][0])
    e_cash = np.asarray(project(_plan(extra="500")).components["cash"][0])
    assert e_cash[a_year_in] < b_cash[a_year_in]


def test_repaying_early_leaves_the_household_richer_in_the_end() -> None:
    """The aflossen case in one assertion.

    The interest never paid outweighs the cash paid out, so by the horizon the repaying
    household is ahead — which is exactly the comparison aflossen-vs-beleggen puts
    against investing the same money instead.
    """
    base = project(_plan())
    extra = project(_plan(extra="500"))
    assert float(extra.net_worth[0][-1]) > float(base.net_worth[0][-1])


def test_nothing_happens_before_the_milestone_fires() -> None:
    """A repayment dated 2030 must not touch the 2027 balance."""
    early = _debt(project(_plan(extra="500", from_date=date(2027, 1, 1))))
    late = _debt(project(_plan(extra="500", from_date=date(2030, 1, 1))))
    months_to_2029 = (2029 - 2026) * 12
    assert early[months_to_2029] < late[months_to_2029]


def test_an_extra_repayment_without_a_mortgage_is_a_no_op() -> None:
    """No house, nothing to repay — and no crash on an absent balance."""
    plan = _plan()
    no_house = plan.__class__(
        household=plan.household,
        people=plan.people,
        accounts=plan.accounts,
        cash_flows=plan.cash_flows,
        milestones=[
            Milestone(
                id=2,
                household_id=1,
                label="aflossen",
                on_date=date(2027, 1, 1),
                params=ExtraRepayment(monthly_amount=Decimal(500)),
            )
        ],
        start=plan.start,
        assumptions=plan.assumptions,
    )
    proj = project(no_house)
    assert np.all(np.asarray(proj.components["debt"][0]) == 0.0)


def test_the_extra_never_overpays_the_remaining_balance() -> None:
    """A repayment larger than what is left clears it exactly, never past zero."""
    proj = project(_plan(extra="200000"))
    debt = _debt(proj)
    assert debt.min() >= -1e-6
    assert debt[-1] <= 0.01


def test_the_template_reaches_the_engine_through_a_scenario() -> None:
    """The whole aflossen-vs-beleggen path, not just the engine hook.

    The template ships the milestone as an `added_milestones` entry inside a scenario, so
    it has to survive pydantic's discriminated union and `apply_scenario` before the
    engine ever sees it. That validation seam is where a new milestone type breaks.
    """
    plan = _plan()
    scenario = Scenario(
        id=1,
        household_id=1,
        name="Aflossen 500/mo",
        overrides=ScenarioOverrides(
            added_milestones=[
                {
                    "id": -1,
                    "household_id": 1,
                    "label": "aflossen",
                    "on_date": "2027-01-01",
                    "params": {"type": "extra_repayment", "monthly_amount": "500.00"},
                }
            ]
        ),
    )
    applied, _ = apply_scenario(plan, scenario)
    assert len(applied.milestones) == len(plan.milestones) + 1  # applied by the caller
    with_extra = _debt(project(applied))
    without = _debt(project(_plan()))
    assert with_extra[MID] < without[MID]
