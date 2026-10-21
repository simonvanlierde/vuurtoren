"""The solve-for-X bisection: it inverts the pure `project()` for a knob that hits a goal."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from itertools import pairwise
from typing import TYPE_CHECKING

import numpy as np
from tests.test_engine import simple_plan

from vuurtoren.domain import CashFlow, CashFlowKind
from vuurtoren.engine import project, projection_months
from vuurtoren.solve import (
    FireBy,
    NetWorthAt,
    SuccessAtLeast,
    _scaled,
    baseline_monthly,
    solve,
    sweep,
    tornado,
)

if TYPE_CHECKING:
    from vuurtoren.engine import PlanInput

_EXPENSE = CashFlow(
    id=1, household_id=1, label="Living", amount_monthly=Decimal(2000), kind=CashFlowKind.EXPENSE
)
_CONTRIBUTION = CashFlow(
    id=2,
    household_id=1,
    label="Invest",
    amount_monthly=Decimal(1000),
    kind=CashFlowKind.CONTRIBUTION,
    target_account_id=2,  # the equity account in simple_plan — else it drains into the void
)


def _plan() -> PlanInput:
    return simple_plan(cash_flows=[_EXPENSE, _CONTRIBUTION])


def test_baseline_monthly_sums_the_knobs_kind() -> None:
    """The baseline is the total of the plan's flows of the knob's kind, not both."""
    plan = _plan()
    assert baseline_monthly(plan, "monthly_spending") == Decimal(2000)
    assert baseline_monthly(plan, "monthly_contributions") == Decimal(1000)


def test_baseline_monthly_counts_only_flows_running_at_the_start() -> None:
    """An ended or future flow is not part of today's spending.

    Summing every EXPENSE flow counted a rent that already ended and a childcare cost
    years away as spending now, so the solver's baseline read too high.
    """
    plan = _plan()
    ended = _EXPENSE.model_copy(update={"id": 3, "end_date": plan.start.replace(year=2020)})
    future = _EXPENSE.model_copy(update={"id": 4, "start_date": plan.start.replace(year=2040)})
    plan = replace(plan, cash_flows=[*plan.cash_flows, ended, future])
    assert baseline_monthly(plan, "monthly_spending") == Decimal(2000)


def test_die_with_zero_finds_a_spending_that_depletes_by_the_year() -> None:
    """Solve the spending that lands run-0 net worth on ~0 in the chosen year."""
    # NetWorthAt(at_least=0) is die-with-zero; more spending → lower end worth (monotone).
    result = solve(_plan(), "monthly_spending", NetWorthAt(year=2060, at_least=0.0))
    assert result.converged
    assert result.solved_monthly is not None
    assert result.achieved is not None
    # The knob converges to €0.50/mo and the solve keeps the side that meets the goal, so
    # the residual is never negative and is what half a euro a month compounds to.
    assert 0 <= result.achieved < 1_000
    assert Decimal(400) < result.solved_monthly < Decimal(415)


def test_fire_by_finds_the_contribution_that_reaches_fi_in_the_year() -> None:
    """Solving contributions for a FI-by year lands the realised FI date on that year."""
    target = 2045
    result = solve(_plan(), "monthly_contributions", FireBy(year=target))
    assert result.converged
    assert result.solved_monthly is not None
    assert result.solved_monthly > 0
    assert result.achieved is not None
    # Realised FI year lands on the target boundary (integer-month root).
    assert abs(result.achieved - target) <= 1


def test_fire_by_solves_spending_on_a_plan_with_income() -> None:
    """Spending 0 is FI at once, so the spending bracket opens on the right side.

    Zero spending made the FIRE number zero, which the engine reports as no FI date, so
    the low end read as "never" and no bracket could straddle the target.
    """
    salary = CashFlow(
        id=3, household_id=1, label="Salary", amount_monthly=Decimal(4000), kind=CashFlowKind.INCOME
    )
    result = solve(simple_plan(cash_flows=[salary, _EXPENSE]), "monthly_spending", FireBy(2045))
    assert result.converged
    assert result.achieved is not None
    assert result.achieved <= 2045


def test_a_success_target_of_one_keeps_the_whole_plateau() -> None:
    """Every spending up to some level is fully safe; the solve returns the top of that.

    A tie at the target used to move the high end down, bisecting the plateau to zero.
    """
    result = solve(_plan(), "monthly_spending", SuccessAtLeast(probability=1.0, n_runs=50))
    assert result.converged
    assert result.achieved == 1.0
    assert result.solved_monthly is not None
    assert result.solved_monthly > Decimal(100)


def test_a_bequest_floor_lowers_the_spending_a_success_target_allows() -> None:
    """With a floor, a run succeeds only if it also ends at or above it, as in Monte Carlo."""
    plain = solve(_plan(), "monthly_spending", SuccessAtLeast(probability=1.0, n_runs=50))
    assert plain.solved_monthly is not None
    # Above what the poorest run leaves at the plain answer: that spending now fails.
    at_plain = project(
        _scaled(_plan(), "monthly_spending", plain.solved_monthly, plain.baseline_monthly),
        n_runs=50,
        seed=0,
    )
    floor = float(at_plain.net_worth[:, -1].min()) + 50_000.0
    floored = solve(
        _plan(),
        "monthly_spending",
        SuccessAtLeast(probability=1.0, n_runs=50, min_end_net_worth=floor),
    )
    assert floored.converged
    assert floored.achieved == 1.0
    assert floored.solved_monthly is not None
    assert floored.solved_monthly < plain.solved_monthly


def test_no_flows_of_the_kind_does_not_converge() -> None:
    """A €0 baseline (no flows of the kind) declines rather than dividing by zero."""
    result = solve(simple_plan(cash_flows=[_EXPENSE]), "monthly_contributions", FireBy(year=2045))
    assert not result.converged
    assert result.solved_monthly is None


def test_sweep_returns_a_non_increasing_success_curve() -> None:
    """Sweeping spending from 0 upward gives a success curve that never rises."""
    rows = sweep(_plan(), "monthly_spending", points=6, n_runs=64)
    assert len(rows) == 6
    assert rows[0].monthly == Decimal("0.00")
    successes = [r.success for r in rows]
    assert all(a >= b for a, b in pairwise(successes))


def test_sweep_points_match_independent_projections_exactly() -> None:
    """Sharing one returns provider across the sweep changes nothing.

    Each point must be bit-for-bit the projection a fresh `project` call with the same
    seed would give.
    """
    plan = _plan()
    rows = sweep(plan, "monthly_spending", points=4, n_runs=64, seed=3)
    for row in rows:
        fresh = project(
            _scaled(plan, "monthly_spending", row.monthly, Decimal(2000)), n_runs=64, seed=3
        )
        assert row.median_end_worth == float(np.median(fresh.net_worth[:, -1]))


def test_projection_months_are_the_months_a_projection_reports() -> None:
    """The horizon comes without running the projection, and agrees with it."""
    assert projection_months(_plan()) == project(_plan()).months


def test_sweep_of_a_zero_baseline_knob_is_empty() -> None:
    """No flows of the kind means nothing to sweep — an empty curve, not a crash."""
    assert sweep(simple_plan(cash_flows=[_EXPENSE]), "monthly_contributions", points=6) == []


# --- sensitivity tornado ---


def test_tornado_returns_a_row_per_applicable_knob_sorted_widest_first() -> None:
    """Every knob the plan can express gets a row, ranked by how far the metric moved.

    `house_appreciation` is absent: this plan owns no property, so it is not a question
    the household faces rather than one whose answer is zero.
    """
    rows = tornado(_plan(), metric="end_net_worth")
    assert {r.knob for r in rows} == {"return_assumption", "inflation", "swr"}
    widths = [abs(r.high - r.low) for r in rows if r.low is not None and r.high is not None]
    assert widths == sorted(widths, reverse=True)


def test_tornado_ranking_is_not_assumed_to_favour_the_return_assumption() -> None:
    """Which knob wins is data, not doctrine.

    On this plan a 1pp inflation move beats a 1pp return move, because inflation
    compounds on the expense stream across the whole horizon while the return only works
    on the balance accumulated so far. That is exactly the kind of prior the tornado
    exists to overturn, so the ranking is asserted to be *computed*, never hard-coded.
    """
    rows = tornado(_plan(), metric="end_net_worth")
    assert rows[0].knob == "inflation"


def test_tornado_states_the_delta_it_used() -> None:
    """A bar width means nothing without the perturbation that produced it."""
    rows = tornado(_plan(), metric="end_net_worth")
    assert {r.delta for r in rows if r.knob == "swr"} == {0.005}
    assert {r.delta for r in rows if r.knob == "inflation"} == {0.01}


def test_tornado_higher_return_gives_the_higher_end_worth() -> None:
    """`low`/`high` follow the knob's direction, so a bar is never drawn backwards."""
    row = next(r for r in tornado(_plan(), metric="end_net_worth") if r.knob == "return_assumption")
    assert row.low is not None
    assert row.high is not None
    assert row.high > row.low


def test_tornado_end_worth_is_in_real_terms() -> None:
    """More inflation leaves less to spend, so its high side ends lower.

    Measured in nominal euros the same plan ended *richer* under more inflation, because
    inflation-linked balances grow in step with prices, and the bar pointed the wrong way.
    """
    saver = simple_plan(
        cash_flows=[
            CashFlow(
                id=1,
                household_id=1,
                label="Salary",
                amount_monthly=Decimal(5000),
                kind=CashFlowKind.INCOME,
                inflation_linked=True,
            ),
            _EXPENSE.model_copy(update={"inflation_linked": True}),
        ]
    )
    row = next(r for r in tornado(saver, metric="end_net_worth") if r.knob == "inflation")
    assert row.low is not None
    assert row.high is not None
    assert row.high < row.low


def test_tornado_drops_a_knob_the_plan_cannot_express() -> None:
    """No account assumes a return, so the return row is absent rather than zero-width.

    "Not applicable" and "does not matter" are different answers; a zero-width bar would
    tell the household the return assumption is irrelevant to them.
    """
    plan = _plan()
    flat = replace(
        plan, accounts=[a.model_copy(update={"return_assumption": 0.0}) for a in plan.accounts]
    )
    assert not [r for r in tornado(flat, metric="end_net_worth") if r.knob == "return_assumption"]


def test_tornado_does_not_mutate_the_plan() -> None:
    """Each row is a fresh scenario application; the caller's plan is untouched."""
    plan = _plan()
    before = [a.return_assumption for a in plan.accounts]
    tornado(plan, metric="end_net_worth")
    assert [a.return_assumption for a in plan.accounts] == before


def test_tornado_drops_house_appreciation_without_property() -> None:
    """No property means the house knob is not asked, rather than answered with zero.

    The example household has no real estate, and a zero-width "house appreciation" bar
    would read as a finding ("it turns out not to matter") when the truth is that the
    question does not apply.
    """
    assert not [
        r for r in tornado(_plan(), metric="end_net_worth") if r.knob == "house_appreciation"
    ]
