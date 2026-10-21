"""CodSpeed benchmarks for the projection engine and the solvers built on it."""

from typing import TYPE_CHECKING

from vuurtoren.domain import Scenario, ScenarioOverrides
from vuurtoren.engine import historical_returns, project
from vuurtoren.scenarios import apply_scenario
from vuurtoren.solve import tornado

if TYPE_CHECKING:
    from pytest_codspeed import BenchmarkFixture

    from vuurtoren.engine import PlanInput

MC_RUNS = 100


def test_project_deterministic_nl(benchmark: BenchmarkFixture, nl_plan: PlanInput) -> None:
    """One fixed-return projection of the Dutch household (the Plan page)."""
    proj = benchmark(project, nl_plan)
    assert proj.net_worth.shape[0] == 1


def test_project_deterministic_us(benchmark: BenchmarkFixture, us_plan: PlanInput) -> None:
    """One fixed-return projection with the US overlay active."""
    proj = benchmark(project, us_plan)
    assert proj.net_worth.shape[0] == 1


def test_project_monte_carlo_gaussian(benchmark: BenchmarkFixture, nl_plan: PlanInput) -> None:
    """A seeded Gaussian Monte Carlo projection."""
    proj = benchmark(project, nl_plan, n_runs=MC_RUNS, seed=1)
    assert proj.net_worth.shape[0] == MC_RUNS


def test_project_monte_carlo_historical(benchmark: BenchmarkFixture, nl_plan: PlanInput) -> None:
    """A Monte Carlo projection on block-bootstrapped historical returns."""
    proj = benchmark(lambda: project(nl_plan, n_runs=MC_RUNS, returns=historical_returns(1)))
    assert proj.net_worth.shape[0] == MC_RUNS


def test_apply_scenario_and_project(benchmark: BenchmarkFixture, nl_plan: PlanInput) -> None:
    """Applying a scenario's overrides, then projecting it (the scenario compare view)."""
    scenario = Scenario(
        id=1,
        household_id=nl_plan.household.id,
        name="bench",
        overrides=ScenarioOverrides(assumptions={"house_appreciation": 0.03, "inflation": 0.025}),
    )

    def run() -> object:
        applied, tax = apply_scenario(nl_plan, scenario)
        return project(applied, tax_overrides=tax)

    assert benchmark(run) is not None


def test_tornado(benchmark: BenchmarkFixture, nl_plan: PlanInput) -> None:
    """The sensitivity tornado: two deterministic projections per applicable knob."""
    rows = benchmark(tornado, nl_plan, metric="end_net_worth")
    assert rows
