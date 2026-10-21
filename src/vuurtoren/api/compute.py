"""The projection endpoints: project, solve, retirement, sweep and sensitivity."""

import secrets
from typing import TYPE_CHECKING, Any

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from vuurtoren.api.deps import SessionDep, plan_errors_as_400, planned
from vuurtoren.api.schemas import (
    MonteCarloOut,
    ProjectionOut,
    ProjectRequest,
    RetirementOut,
    RetirementRequest,
    SensitivityOut,
    SensitivityRequest,
    SolveGoal,
    SolveOut,
    SolveRequest,
    SweepOut,
    SweepRequest,
)
from vuurtoren.engine import (
    Projection,
    historical_returns,
    project,
    sequential_returns,
)
from vuurtoren.mortality import household_survival
from vuurtoren.returns_data import START_YEARS
from vuurtoren.solve import (
    FireBy,
    NetWorthAt,
    SuccessAtLeast,
    baseline_monthly,
    retirement_success,
    solve,
    solve_retirement,
    sweep,
    tornado,
    tornado_metric,
)

if TYPE_CHECKING:
    from datetime import date

    from vuurtoren import domain

router = APIRouter()

# Each route names JSONResponse explicitly. Left at the default, FastAPI serialises a
# response_model with pydantic's own JSON writer, which spells floats differently from
# Python's json (0.00001 against 1e-05), and every float here is a chart value.

_MAX_SOLVE_RUNS = 2000
_MAX_SWEEP_POINTS = 60


def _household_survival(p: Projection, people: list[domain.Person], start: date) -> list[float]:
    """P(at least one person alive) per month, from the CBS life table."""
    ages = [(start - person.birth_date).days / 365.25 for person in people]
    return household_survival(ages, len(p.months)).tolist()


def _serialize_projection(
    p: Projection,
    *,
    seed: int | None = None,
    mode: str = "gaussian",
    min_end_net_worth: float | None = None,
    start_years: list[int] | None = None,
    survival: list[float] | None = None,
) -> dict[str, Any]:
    n_runs = p.net_worth.shape[0]
    if n_runs > 1:
        # The Monte Carlo shape: percentile bands and a success
        # probability, not n_runs x n_months of JSON. The seed and mode are echoed so
        # every chart is reproducible and labelled with the model that produced it.
        p10, p50, p90 = np.percentile(p.net_worth, [10, 50, 90], axis=0)
        return {
            "months": [m.isoformat() for m in p.months],
            "inflation_factor": p.inflation_factor.tolist(),
            "n_runs": n_runs,
            "seed": seed,
            "mode": mode,
            # Sequential mode only: run r *is* start year start_years[r], which is what
            # makes "which start years fail?" answerable. None under the sampling modes —
            # a bootstrapped run has no calendar name to give.
            "start_years": start_years,
            "bands": {"p10": p10.tolist(), "p50": p50.tolist(), "p90": p90.tolist()},
            "success_probability": p.success_probability(min_end_net_worth),
            # The mortality overlay's two inputs: how many runs are still
            # solvent each month, and how likely the household is to be alive to see it.
            "solvent_fraction": p.solvent_fraction(),
            "survival": survival,
            "flow_totals": {k: v.tolist() for k, v in p.flow_totals.items()},
            "fire": {
                "fire_number": p.fire.fire_number,
                "savings_rate": p.fire.savings_rate,
                # Per-run FI dates drive the FIRE-date histogram — the "when", not just the
                # net-worth percentiles. None = that run never reached FI (its own bucket).
                "fi_dates": [d.isoformat() if d else None for d in p.fire.fi_dates],
                "net_swr": p.fire.net_swr,
            },
        }
    return {
        "months": [m.isoformat() for m in p.months],
        "inflation_factor": p.inflation_factor.tolist(),
        "flow_totals": {k: v.tolist() for k, v in p.flow_totals.items()},
        "net_worth": p.net_worth.tolist(),
        "components": {k: v.tolist() for k, v in p.components.items()},
        "tax_paid": {k: v.tolist() for k, v in p.tax_paid.items()},
        "one_off_costs": {k: v.tolist() for k, v in p.one_off_costs.items()},
        "investment_income": p.investment_income.tolist(),
        "fire": {
            "fire_number": p.fire.fire_number,
            "fi_dates": [d.isoformat() if d else None for d in p.fire.fi_dates],
            "coast_fire_dates": [d.isoformat() if d else None for d in p.fire.coast_fire_dates],
            "savings_rate": p.fire.savings_rate,
            "fire_usable": p.fire.fire_usable.tolist(),
            "net_swr": p.fire.net_swr,
        },
        "cash_shortfall": [d.isoformat() if d else None for d in p.cash_shortfall],
    }


@router.post(
    "/api/project", response_model=ProjectionOut | MonteCarloOut, response_class=JSONResponse
)
def run_projection(body: ProjectRequest, session: SessionDep) -> dict[str, Any]:
    """Assemble a PlanInput from the database and run the projection."""
    historical = body.mode == "historical"
    sequential = body.mode == "sequential"
    if historical and body.n_runs <= 1:
        raise HTTPException(
            status_code=400,
            detail="historical mode needs n_runs > 1: the deterministic path does not bootstrap",
        )
    # Sequential runs are the dataset's start years, so the caller does not get to pick
    # n_runs — the data does — and there is no rng to seed. Both are echoed as what ran.
    n_runs = len(START_YEARS) if sequential else body.n_runs
    seed = None if sequential else body.seed
    if n_runs > 1 and not sequential and seed is None:
        seed = secrets.randbits(32)
    # gaussian is project()'s own default for n_runs > 1, so only the other two
    # providers are passed explicitly.
    returns = None
    if sequential:
        returns = sequential_returns()
    elif n_runs > 1 and historical:
        returns = historical_returns(seed)
    plan, tax_overrides = planned(session, body)
    with plan_errors_as_400():
        projection = project(
            plan, n_runs=n_runs, seed=seed, returns=returns, tax_overrides=tax_overrides
        )

    return _serialize_projection(
        projection,
        seed=seed,
        mode=body.mode,
        min_end_net_worth=body.min_end_net_worth,
        start_years=list(START_YEARS) if sequential else None,
        survival=_household_survival(projection, plan.people, body.start) if n_runs > 1 else None,
    )


def _to_solve_goal(g: SolveGoal) -> FireBy | NetWorthAt | SuccessAtLeast:
    """Validate the request goal into a solve.Goal, 400ing on a shape its type lacks."""
    if g.type == "fire_by":
        if g.year is None:
            raise HTTPException(status_code=400, detail="fire_by needs a year")
        return FireBy(year=g.year)
    if g.type == "net_worth_at":
        if g.year is None or g.at_least is None:
            raise HTTPException(status_code=400, detail="net_worth_at needs year and at_least")
        return NetWorthAt(year=g.year, at_least=g.at_least)
    if g.probability is None:
        raise HTTPException(status_code=400, detail="success_at_least needs probability")
    return SuccessAtLeast(
        probability=g.probability,
        n_runs=min(g.n_runs, _MAX_SOLVE_RUNS),
        min_end_net_worth=g.min_end_net_worth,
    )


@router.post("/api/solve", response_model=SolveOut, response_class=JSONResponse)
def run_solve(body: SolveRequest, session: SessionDep) -> dict[str, Any]:
    """Solve for the monthly spending/contribution that hits a goal.

    Bisects the pure projection ("solve for X", die-with-zero).
    """
    goal = _to_solve_goal(body.goal)
    plan, tax_overrides = planned(session, body)
    with plan_errors_as_400():
        result = solve(plan, body.knob, goal, tax_overrides=tax_overrides)
    return {
        "knob": result.knob,
        "baseline_monthly": float(result.baseline_monthly),
        "solved_monthly": None if result.solved_monthly is None else float(result.solved_monthly),
        "achieved": result.achieved,
        "converged": result.converged,
    }


@router.post("/api/retirement", response_model=RetirementOut, response_class=JSONResponse)
def run_retirement(body: RetirementRequest, session: SessionDep) -> dict[str, Any]:
    """Solve for a retirement date, or report the odds of one.

    The answer deliberately differs from `fire.fi_dates`: that is net worth crossing the
    4%-rule `fire_number`, this is the simulated date with AOW timing, pension unlock and
    Box 3 drag in play. Both travel back so the UI can show them side by side.
    """
    if (body.at_date is None) == (body.probability is None):
        raise HTTPException(status_code=400, detail="send exactly one of at_date or probability")
    plan, tax_overrides = planned(session, body)
    n_runs = min(body.n_runs, _MAX_SOLVE_RUNS)
    with plan_errors_as_400():
        if body.at_date is not None:
            at_month = (body.at_date.year - body.start.year) * 12 + (
                body.at_date.month - body.start.month
            )
            result = retirement_success(
                plan,
                at_month=at_month,
                person_ids=body.person_ids,
                residual_monthly=body.residual_monthly,
                n_runs=n_runs,
                tax_overrides=tax_overrides,
            )
        else:
            # Narrowing for the type checker: the guard above already proved exactly one
            # of the two is set, but it cannot see that through the equality.
            probability = body.probability if body.probability is not None else 0.0
            result = solve_retirement(
                plan,
                person_ids=body.person_ids,
                residual_monthly=body.residual_monthly,
                probability=probability,
                n_runs=n_runs,
                tax_overrides=tax_overrides,
            )
    return {
        "retire_date": None if result.retire_date is None else result.retire_date.isoformat(),
        "achieved": result.achieved,
        "fi_date": None if result.fi_date is None else result.fi_date.isoformat(),
        "converged": result.converged,
    }


@router.post("/api/sweep", response_model=SweepOut, response_class=JSONResponse)
def run_sweep(body: SweepRequest, session: SessionDep) -> dict[str, Any]:
    """Sweep the knob and return the spending-vs-success curve."""
    plan, tax_overrides = planned(session, body)
    with plan_errors_as_400():
        rows = sweep(
            plan,
            body.knob,
            points=min(body.points, _MAX_SWEEP_POINTS),
            n_runs=min(body.n_runs, _MAX_SOLVE_RUNS),
            tax_overrides=tax_overrides,
        )
    return {
        "knob": body.knob,
        "baseline_monthly": float(baseline_monthly(plan, body.knob)),
        "points": [
            {"monthly": float(r.monthly), "success": r.success, "end_worth": r.median_end_worth}
            for r in rows
        ],
    }


@router.post("/api/sensitivity", response_model=SensitivityOut, response_class=JSONResponse)
def run_sensitivity(body: SensitivityRequest, session: SessionDep) -> dict[str, Any]:
    """Rank the assumptions by how far each one moves the metric (the tornado)."""
    plan, tax_overrides = planned(session, body)
    with plan_errors_as_400():
        rows = tornado(plan, metric=body.metric, tax_overrides=tax_overrides)
        baseline = project(plan, n_runs=1, tax_overrides=tax_overrides)
    return {
        "metric": body.metric,
        # The zero-line every bar is drawn against. None when the metric is a FI year the
        # baseline never reaches — the chart must say so rather than centre on nothing.
        "baseline": tornado_metric(body.metric, baseline),
        "rows": [{"knob": r.knob, "delta": r.delta, "low": r.low, "high": r.high} for r in rows],
    }
