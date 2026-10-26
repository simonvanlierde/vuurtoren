"""CodSpeed benchmarks for the projection engine and the solvers built on it.

Monte Carlo runs at the 1000 runs the UI asks for: a run costs far less than the
per-month work every projection shares, so a small run count would hide a regression
in the vectorised path.
"""

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from vuurtoren.engine import gaussian_returns, historical_returns, project, sequential_returns
from vuurtoren.returns_data import START_YEARS
from vuurtoren.solve import FireBy, solve, solve_retirement

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_codspeed import BenchmarkFixture

    from vuurtoren.engine import PlanInput, ReturnsProvider

MC_RUNS = 1000


def test_project_deterministic_nl(benchmark: BenchmarkFixture, nl_plan: PlanInput) -> None:
    """One fixed-return projection of the Dutch household (the Plan page)."""
    proj = benchmark(project, nl_plan)
    assert proj.net_worth.shape[0] == 1


def test_project_deterministic_us(benchmark: BenchmarkFixture, us_plan: PlanInput) -> None:
    """One fixed-return projection with the US overlay active."""
    proj = benchmark(project, us_plan)
    assert proj.net_worth.shape[0] == 1


@pytest.mark.parametrize(
    ("returns", "n_runs"),
    [
        pytest.param(lambda: gaussian_returns(1), MC_RUNS, id="gaussian"),
        pytest.param(lambda: historical_returns(1), MC_RUNS, id="historical"),
        pytest.param(sequential_returns, len(START_YEARS), id="sequential"),
    ],
)
def test_project_monte_carlo(
    benchmark: BenchmarkFixture,
    nl_plan: PlanInput,
    returns: Callable[[], ReturnsProvider],
    n_runs: int,
) -> None:
    """A Monte Carlo projection under each returns mode the API offers."""
    proj = benchmark(lambda: project(nl_plan, n_runs=n_runs, returns=returns()))
    assert proj.net_worth.shape[0] == n_runs


def test_solve_fire_by(benchmark: BenchmarkFixture, nl_plan: PlanInput) -> None:
    """Bisect monthly spending until FI lands in 2045: a dozen deterministic projections."""
    result = benchmark(solve, nl_plan, "monthly_spending", FireBy(year=2045))
    assert result.converged


def test_solve_retirement(benchmark: BenchmarkFixture, nl_plan: PlanInput) -> None:
    """Bisect the earliest retirement month that holds 90% success (the early-retirement panel)."""
    person_ids = [p.id for p in nl_plan.people]
    result = benchmark(
        solve_retirement,
        nl_plan,
        person_ids=person_ids,
        residual_monthly=Decimal(0),
        probability=0.9,
        n_runs=MC_RUNS,
    )
    assert result.converged
