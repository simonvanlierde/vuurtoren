"""The early-retirement solver: bisect the retirement month, not a euro amount."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from test_engine import simple_plan
from test_solve import _HEAVY_TAX
from vuurtoren.domain import (
    Account,
    AccountKind,
    CashFlow,
    CashFlowKind,
    Household,
    IncomeChange,
    Milestone,
    Person,
)
from vuurtoren.engine import Assumptions, project, projection_months
from vuurtoren.solve import retire_at, retirement_success, solve_retirement

if TYPE_CHECKING:
    from vuurtoren.engine import PlanInput


def _plan(*, salary: str = "5000", spend: str = "2500", equity: str = "400000") -> PlanInput:
    """One earner, one spender, one pot — enough for retirement to be a real question."""
    household = Household(id=1, name="T", fiscal_partners=False, life_expectancy_age=90)
    people = [Person(id=1, household_id=1, name="A", birth_date=date(1990, 1, 1))]
    accounts = [
        Account(
            id=2,
            household_id=1,
            owner_person_id=1,
            name="Cash",
            kind=AccountKind.CASH,
            tax_treatment="nl.box3_bank",
            manual_value=Decimal(20000),
            return_assumption=0.0,
        ),
        Account(
            id=1,
            household_id=1,
            owner_person_id=1,
            name="Equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.box3_investment",
            manual_value=Decimal(equity),
            return_assumption=0.06,
            volatility_assumption=0.15,
        ),
    ]
    flows = [
        CashFlow(
            id=1,
            household_id=1,
            owner_person_id=1,
            label="salary",
            amount_monthly=Decimal(salary),
            kind=CashFlowKind.INCOME,
            inflation_linked=True,
        ),
        CashFlow(
            id=2,
            household_id=1,
            label="living",
            amount_monthly=Decimal(spend),
            kind=CashFlowKind.EXPENSE,
            inflation_linked=True,
        ),
    ]
    return simple_plan(household=household, people=people, accounts=accounts, cash_flows=flows)


def test_retire_at_zeroes_the_owned_income_flow() -> None:
    """Residual 0 reproduces Retire: the person's own income stops, nothing else moves."""
    plan = _plan()
    out = retire_at(plan, 60, person_ids=[1], residual_monthly=Decimal(0))
    added = [m for m in out.milestones if m not in plan.milestones]
    assert len(added) == 1
    params = added[0].params
    assert isinstance(params, IncomeChange)
    assert params.new_amount_monthly == Decimal(0)
    # The salary itself ends in the retirement month; the change sets its continuation.
    flows = {f.id: f for f in out.cash_flows}
    assert flows[1].end_date == date(2031, 1, 1)
    assert flows[params.cash_flow_id].start_date == date(2031, 2, 1)


def test_retire_at_keeps_a_residual_for_barista() -> None:
    """BaristaFIRE is the same milestone with a non-zero amount — not a second path."""
    out = retire_at(_plan(), 60, person_ids=[1], residual_monthly=Decimal(1500))
    added = [m.params for m in out.milestones if isinstance(m.params, IncomeChange)]
    assert added[0].new_amount_monthly == Decimal(1500)


def test_retire_at_leaves_flows_owned_by_others_alone() -> None:
    """Per-person: solving one person's date must not silently retire the household."""
    plan = _plan()
    other = plan.cash_flows[0].model_copy(update={"id": 9, "owner_person_id": 2})
    plan = replace(plan, cash_flows=[*plan.cash_flows, other])
    out = retire_at(plan, 60, person_ids=[1], residual_monthly=Decimal(0))
    ended = {f.id for f in out.cash_flows if f.end_date is not None}
    assert ended == {1}


def test_retire_at_splits_the_residual_across_several_owned_flows() -> None:
    """Two salaries, one residual: shares are preserved, and they sum to the residual."""
    plan = _plan()
    second = plan.cash_flows[0].model_copy(
        update={"id": 9, "amount_monthly": Decimal(5000), "label": "bonus"}
    )
    plan = replace(plan, cash_flows=[*plan.cash_flows, second])
    out = retire_at(plan, 60, person_ids=[1], residual_monthly=Decimal(2000))
    amounts = [
        p.new_amount_monthly
        for p in (m.params for m in out.milestones)
        if isinstance(p, IncomeChange)
    ]
    assert sum(amounts) == Decimal(2000)
    assert amounts[0] == amounts[1]  # equal salaries -> equal halves


def _with_a_later_raise(plan: PlanInput) -> PlanInput:
    """`plan` with a stored raise to 7,000 a month that fires ten years in."""
    raise_ = Milestone(
        id=1,
        household_id=1,
        label="promotion",
        on_date=date(plan.start.year + 10, 1, 1),
        params=IncomeChange(cash_flow_id=1, new_amount_monthly=Decimal(7000)),
    )
    return replace(plan, milestones=[raise_])


def test_a_later_raise_does_not_bring_a_retired_salary_back() -> None:
    """Retiring at month 60 stops the salary for good, as a Retire milestone would.

    The retirement was an IncomeChange to zero, so a stored raise firing after it set the
    salary to 7,000 again and the "retired" person went back to work.
    """
    plan = _with_a_later_raise(_plan())
    income = project(retire_at(plan, 60, person_ids=[1], residual_monthly=Decimal(0)))
    assert income.flow_totals["income"][62:].max() == 0.0


def test_a_later_raise_does_not_replace_a_barista_residual() -> None:
    """The residual is what the person earns after retiring, whatever the old job did."""
    plan = replace(_with_a_later_raise(_plan()), assumptions=Assumptions(inflation=0.0))
    income = project(retire_at(plan, 60, person_ids=[1], residual_monthly=Decimal(1500)))
    assert income.flow_totals["income"][62:].max() == 1500.0
    assert income.flow_totals["income"][1:61].min() == 5000.0


def test_retire_at_with_no_owned_income_changes_nothing() -> None:
    """Nothing to retire from is not a division by zero."""
    plan = _plan()
    out = retire_at(plan, 60, person_ids=[99], residual_monthly=Decimal(0))
    assert out.milestones == plan.milestones


def test_solving_finds_a_date_and_it_clears_the_target() -> None:
    """The solved month actually achieves the requested probability."""
    r = solve_retirement(
        _plan(), person_ids=[1], residual_monthly=Decimal(0), probability=0.85, n_runs=200
    )
    assert r.converged
    assert r.retire_date is not None
    assert r.achieved is not None
    assert r.achieved >= 0.80  # bisection tolerance, not an exact equality


def test_retiring_later_is_never_worse() -> None:
    """The monotonicity the bisection rests on, asserted rather than assumed."""
    plan = _plan()
    early = retirement_success(
        plan, at_month=60, person_ids=[1], residual_monthly=Decimal(0), n_runs=200
    )
    late = retirement_success(
        plan, at_month=300, person_ids=[1], residual_monthly=Decimal(0), n_runs=200
    )
    assert late.achieved is not None
    assert early.achieved is not None
    assert late.achieved >= early.achieved


def test_a_residual_beats_retiring_outright_on_the_same_date() -> None:
    """BaristaFIRE is strictly easier than full FIRE, which is the whole point of it."""
    plan = _plan()
    full = retirement_success(
        plan, at_month=120, person_ids=[1], residual_monthly=Decimal(0), n_runs=200
    )
    barista = retirement_success(
        plan, at_month=120, person_ids=[1], residual_monthly=Decimal(1500), n_runs=200
    )
    assert barista.achieved is not None
    assert full.achieved is not None
    assert barista.achieved >= full.achieved


def test_an_unreachable_target_does_not_converge() -> None:
    """A household that cannot retire at any date says so, rather than returning month 0.

    It has to be one that fails *while still working*: retiring in the horizon's last
    months is barely retiring at all, so any household still solvent at the end can
    always clear a target by picking a late enough date. Spending above income with no
    pot is the case where no date works.
    """
    poor = _plan(salary="2000", spend="3000", equity="1000")
    r = solve_retirement(
        poor, person_ids=[1], residual_monthly=Decimal(0), probability=0.90, n_runs=100
    )
    assert not r.converged
    assert r.retire_date is None


def test_a_household_that_can_retire_today_gets_month_zero() -> None:
    """Clearing the target at once is an answer, not a failure to converge."""
    rich = _plan(equity="5000000")
    r = solve_retirement(
        rich, person_ids=[1], residual_monthly=Decimal(0), probability=0.5, n_runs=50
    )
    assert r.converged
    assert r.retire_date == rich.start


def test_a_certain_target_returns_the_earliest_month_that_reaches_it() -> None:
    """At p = 1.0 every later month ties at the target; the earliest one is the answer.

    A tie used to move the low end up, so the solve walked to the horizon's last month.
    """
    plan = _plan()
    r = solve_retirement(
        plan, person_ids=[1], residual_monthly=Decimal(0), probability=1.0, n_runs=50
    )
    assert r.converged
    assert r.retire_date is not None
    month = (r.retire_date.year - plan.start.year) * 12 + r.retire_date.month - plan.start.month
    earlier = retirement_success(
        plan, at_month=month - 1, person_ids=[1], residual_monthly=Decimal(0), n_runs=50
    )
    assert earlier.achieved is not None
    assert earlier.achieved < 1.0


def _month_of(plan: PlanInput, d: date) -> int:
    return projection_months(plan).index(d)


def test_retirement_success_reports_the_month_it_was_asked_about() -> None:
    """Month 0 is today; a month past the horizon is clamped to the last one a milestone fits."""
    plan = _plan()
    months = projection_months(plan)
    first = retirement_success(
        plan, at_month=0, n_runs=1, person_ids=[1], residual_monthly=Decimal(0)
    )
    assert first.retire_date == plan.start
    assert first.converged is True
    last = retirement_success(
        plan, at_month=10_000, n_runs=1, person_ids=[1], residual_monthly=Decimal(0)
    )
    assert last.retire_date == months[-2]


def test_a_single_run_retirement_is_the_deterministic_projection() -> None:
    """With one run there is no Monte Carlo: the fixed returns, and run 0's FI date."""
    plan = _plan()
    at = retirement_success(
        plan, at_month=60, n_runs=1, person_ids=[1], residual_monthly=Decimal(0)
    )
    alone = project(retire_at(plan, 60, person_ids=[1], residual_monthly=Decimal(0)))
    assert at.fi_date == alone.fire.fi_dates[0]
    assert at.achieved == alone.success_probability()
    solved = solve_retirement(
        plan, probability=1.0, n_runs=1, person_ids=[1], residual_monthly=Decimal(0)
    )
    assert solved.retire_date is not None
    at_solution = project(
        retire_at(
            plan, _month_of(plan, solved.retire_date), person_ids=[1], residual_monthly=Decimal(0)
        )
    )
    assert solved.fi_date == at_solution.fire.fi_dates[0]


def test_a_seeded_retirement_is_the_seeded_monte_carlo() -> None:
    """Both modes report the success of `n_runs` seeded runs at the date, and run 0's FI date."""
    plan = _plan()
    at = retirement_success(
        plan, at_month=180, n_runs=40, seed=3, person_ids=[1], residual_monthly=Decimal(0)
    )
    runs = project(
        retire_at(plan, 180, person_ids=[1], residual_monthly=Decimal(0)), n_runs=40, seed=3
    )
    success = runs.success_probability()
    assert at.achieved == success
    assert 0.0 < success < 1.0  # a month where the runs disagree, so the seed matters
    assert at.fi_date == runs.fire.fi_dates[0]
    solved = solve_retirement(
        plan, probability=0.5, n_runs=40, seed=3, person_ids=[1], residual_monthly=Decimal(0)
    )
    assert solved.retire_date is not None
    month = _month_of(plan, solved.retire_date)
    runs = project(
        retire_at(plan, month, person_ids=[1], residual_monthly=Decimal(0)), n_runs=40, seed=3
    )
    assert solved.achieved == runs.success_probability()
    assert solved.fi_date == runs.fire.fi_dates[0]


def test_retirement_solves_apply_the_tax_overrides() -> None:
    """A heavier Box 3 pushes the solved date back and the FI date at a fixed date out."""
    plan = _plan()
    taxed = solve_retirement(
        plan,
        probability=1.0,
        n_runs=1,
        tax_overrides=_HEAVY_TAX,
        person_ids=[1],
        residual_monthly=Decimal(0),
    )
    plain = solve_retirement(
        plan, probability=1.0, n_runs=1, person_ids=[1], residual_monthly=Decimal(0)
    )
    assert taxed.retire_date is not None
    assert plain.retire_date is not None
    assert taxed.retire_date > plain.retire_date
    taxed_at = retirement_success(
        plan,
        at_month=120,
        n_runs=1,
        tax_overrides=_HEAVY_TAX,
        person_ids=[1],
        residual_monthly=Decimal(0),
    )
    plain_at = retirement_success(
        plan, at_month=120, n_runs=1, person_ids=[1], residual_monthly=Decimal(0)
    )
    # Untaxed, retiring in 2036 reaches FI; at twice the Box 3 rate it never does.
    assert plain_at.fi_date is not None
    assert taxed_at.fi_date is None


def test_an_unreachable_target_reports_false_not_just_falsy() -> None:
    """`converged` is a bool in the API response, so None would serialise as null."""
    poor = _plan(salary="2000", spend="3000", equity="1000")
    r = solve_retirement(
        poor, probability=0.90, n_runs=1, person_ids=[1], residual_monthly=Decimal(0)
    )
    assert r.converged is False


def test_retire_at_dates_follow_a_mid_year_start() -> None:
    """Month 4 from a July start is November; its continuation starts in December."""
    plan = replace(_plan(), start=date(2026, 7, 1))
    out = retire_at(plan, 4, person_ids=[1], residual_monthly=Decimal(0))
    flows = {f.id: f for f in out.cash_flows}
    assert flows[1].end_date == date(2026, 11, 1)
    added = [m for m in out.milestones if m not in plan.milestones]
    assert [m.on_date for m in added] == [date(2026, 11, 1)]
    assert isinstance(added[0].params, IncomeChange)
    assert flows[added[0].params.cash_flow_id].start_date == date(2026, 12, 1)


def test_retire_at_ids_never_collide_with_stored_ones() -> None:
    """The synthetic flows and milestones exist only in the candidate: their ids are negative."""
    plan = _plan()
    other = plan.cash_flows[0].model_copy(update={"id": 9})
    plan = replace(plan, cash_flows=[*plan.cash_flows, other])
    out = retire_at(plan, 60, person_ids=[1], residual_monthly=Decimal(0))
    added = [m for m in out.milestones if m not in plan.milestones]
    assert sorted(m.id for m in added) == [-2, -1]
