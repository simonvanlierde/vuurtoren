"""Solve for the input that hits a goal, by bisecting the pure `project()`.

"Solve for X" / die-with-zero.

Caller-side only: it rebuilds `PlanInput` with scaled cash flows and never touches the
engine — the same seam `scenarios.py` uses. Every goal metric is monotone in the knob
(more spending → later/no FI, lower end worth, lower success; more contributions the
opposite), so a plain bisection converges. A goal with no solution in the bracket returns
`converged=False` rather than a wrong number.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

import numpy as np

from .domain import (
    AccountKind,
    CashFlowKind,
    IncomeChange,
    Milestone,
    Scenario,
    ScenarioOverrides,
    TaxOverrides,
)
from .engine import flow_active, gaussian_returns, project, projection_months
from .scenarios import apply_scenario

if TYPE_CHECKING:
    from collections.abc import Callable

    from .engine import PlanInput, Projection, ReturnsProvider

Knob = Literal["monthly_spending", "monthly_contributions"]

_KNOB_KIND: dict[Knob, CashFlowKind] = {
    "monthly_spending": CashFlowKind.EXPENSE,
    "monthly_contributions": CashFlowKind.CONTRIBUTION,
}


@dataclass(frozen=True)
class FireBy:
    """Reach FI on or before December of `year`."""

    year: int


@dataclass(frozen=True)
class NetWorthAt:
    """End `year` with at least `at_least` net worth. `at_least=0` is die-with-zero.

    The solve lands as little above it as the bisection resolves, never below.
    """

    year: int
    at_least: float


@dataclass(frozen=True)
class SuccessAtLeast:
    """Hold a Monte Carlo success probability of `probability`.

    Success is `Projection.success_probability`: solvency, and with `min_end_net_worth`
    set, ending with at least that much net worth too.
    """

    probability: float
    n_runs: int = 1000
    min_end_net_worth: float | None = None


Goal = FireBy | NetWorthAt | SuccessAtLeast


@dataclass(frozen=True)
class SolveResult:
    """The solved knob amount and the metric it achieves, or `converged=False`."""

    knob: Knob
    baseline_monthly: Decimal
    solved_monthly: Decimal | None
    achieved: float | None
    """The realised metric at the solution: FI year / end net worth / success fraction."""
    converged: bool


@dataclass(frozen=True)
class _Bisection:
    """The knob-to-metric setup a goal reduces to.

    A monotone `metric(run(monthly))` bisected until it equals `target`.
    """

    run: Callable[[Decimal], Projection]
    metric: Callable[[Projection], float]
    target: float
    max_iter: int
    doublings: int
    at_least: bool
    """The goal is `metric >= target`, not `metric <= target`. See `_solve_root`."""


def _shared_returns(n_runs: int, seed: int) -> ReturnsProvider | None:
    """One Monte Carlo provider for every projection of a search.

    None for a single run, which leaves `project` on its deterministic default.

    `gaussian_returns` draws its shocks lazily, keyed by (month, account kind). Every
    projection of one search has the same accounts, so it asks for the same keys in the
    same order, and a fresh provider would draw exactly the shocks this one has already
    cached. Sharing it is the same answer without redrawing them for each candidate.
    """
    return gaussian_returns(seed) if n_runs > 1 else None


def baseline_monthly(plan: PlanInput, knob: Knob) -> Decimal:
    """Sum of the plan's monthly flows of the knob's kind that run at plan.start."""
    kind = _KNOB_KIND[knob]
    return sum(
        (
            f.amount_monthly
            for f in plan.cash_flows
            if f.kind is kind and flow_active(f, plan.start)
        ),
        Decimal(0),
    )


def _scaled(plan: PlanInput, knob: Knob, monthly: Decimal, baseline: Decimal) -> PlanInput:
    """`plan` with every flow of the knob's kind scaled by `monthly / baseline`.

    The flows running at the start then total `monthly`; a later one scales by the same
    factor, so the household's whole spending moves together.
    """
    kind = _KNOB_KIND[knob]
    factor = monthly / baseline
    flows = [
        f.model_copy(update={"amount_monthly": f.amount_monthly * factor}) if f.kind is kind else f
        for f in plan.cash_flows
    ]
    return replace(plan, cash_flows=flows)


def _month_index_for_year(months: list[date], year: int) -> int:
    """The last month index falling in `year`; clamped to the horizon's ends."""
    idxs = [i for i, m in enumerate(months) if m.year == year]
    if idxs:
        return idxs[-1]
    return len(months) - 1 if year > months[-1].year else 0


def _fi_index(proj: Projection) -> float:
    """Run-0's FI month as an index; `len(months)` (past the horizon) means never.

    No spending means a FIRE number of zero, which the engine reports as no FI date. Here
    it is FI at once: nothing needs funding, and reading it as "never" would put the
    spending knob's low end on the wrong side of every target.
    """
    if proj.fire.fire_number <= 0:
        return 0.0
    d = proj.fire.fi_dates[0]
    return float(proj.months.index(d)) if d is not None else float(len(proj.months))


def _solve_root(
    g: Callable[[Decimal], float],
    target: float,
    baseline: Decimal,
    *,
    max_iter: int,
    doublings: int,
    tol: Decimal,
    at_least: bool,
) -> Decimal | None:
    """Bisect a monotone `g` for the monthly amount where `g(monthly) == target`.

    Brackets by doubling the high end from the baseline until `target` is straddled, then
    halves. Returns None if no bracket straddles the target within `doublings` steps.

    The goal is `g <= target`, or `g >= target` with `at_least`, and a tie meets it: a
    metric that plateaus at the target (a success fraction of 1.0) would otherwise be
    bisected to the far end of the plateau. The end of the final bracket that meets the
    goal is returned, not the midpoint — a step-shaped metric (an FI month, a success
    fraction) can miss the goal half a euro away.
    """
    lo = Decimal(0)
    glo = g(lo)
    hi = max(baseline * 2, Decimal(1))
    for _ in range(doublings):
        ghi = g(hi)
        if min(glo, ghi) <= target <= max(glo, ghi):
            break
        hi *= 2
    else:
        return None

    increasing = ghi >= glo
    for _ in range(max_iter):
        if hi - lo <= tol:
            break
        mid = (lo + hi) / 2
        meets = g(mid) >= target if at_least else g(mid) <= target
        if (meets == increasing) != at_least:
            lo = mid
        else:
            hi = mid
    return hi if increasing == at_least else lo


def _bisection_for(
    plan: PlanInput,
    knob: Knob,
    baseline: Decimal,
    goal: Goal,
    seed: int,
    tax_overrides: TaxOverrides | None,
) -> _Bisection:
    """Reduce a goal to the monotone metric bisected against its target.

    The metric used to *bisect* (fi-index for FireBy) differs from the one *reported* —
    see `_report`.
    """
    if isinstance(goal, SuccessAtLeast):
        returns = _shared_returns(goal.n_runs, seed)

        def run_mc(monthly: Decimal) -> Projection:
            scaled = _scaled(plan, knob, monthly, baseline)
            return project(
                scaled, n_runs=goal.n_runs, seed=seed, returns=returns, tax_overrides=tax_overrides
            )

        return _Bisection(
            run_mc,
            lambda p: p.success_probability(goal.min_end_net_worth),
            goal.probability,
            max_iter=20,
            doublings=12,
            at_least=True,
        )

    def run(monthly: Decimal) -> Projection:
        return project(
            _scaled(plan, knob, monthly, baseline), n_runs=1, tax_overrides=tax_overrides
        )

    if isinstance(goal, FireBy):
        target = float(_month_index_for_year(projection_months(plan), goal.year))
        return _Bisection(run, _fi_index, target, max_iter=40, doublings=24, at_least=False)

    def net_worth_at(proj: Projection) -> float:
        return float(proj.net_worth[0][_month_index_for_year(proj.months, goal.year)])

    return _Bisection(run, net_worth_at, goal.at_least, max_iter=40, doublings=24, at_least=True)


def _fi_year(proj: Projection) -> float | None:
    """Run 0's FI year, or None when it never reaches FI."""
    d = proj.fire.fi_dates[0]
    return float(d.year) if d is not None else None


def _report(goal: Goal, proj: Projection) -> float | None:
    """The realised metric to surface, in the goal's natural unit.

    FI year / end worth / success fraction — not the fi-*index* FireBy bisects on.
    """
    if isinstance(goal, FireBy):
        return _fi_year(proj)
    if isinstance(goal, NetWorthAt):
        return float(proj.net_worth[0][_month_index_for_year(proj.months, goal.year)])
    return proj.success_probability(goal.min_end_net_worth)


def solve(
    plan: PlanInput,
    knob: Knob,
    goal: Goal,
    *,
    seed: int = 0,
    tax_overrides: TaxOverrides | None = None,
) -> SolveResult:
    """Find the monthly knob amount that meets `goal`, by bisecting the pure projection.

    `seed` fixes Monte Carlo noise so the success metric is a deterministic function of
    the knob across the bisection; `tax_overrides` is the `tax` group `apply_scenario`
    hands back, applied to every run.
    """
    baseline = baseline_monthly(plan, knob)
    if baseline <= 0:
        return SolveResult(knob, baseline, None, None, converged=False)

    b = _bisection_for(plan, knob, baseline, goal, seed, tax_overrides)
    solved = _solve_root(
        lambda monthly: b.metric(b.run(monthly)),
        b.target,
        baseline,
        max_iter=b.max_iter,
        doublings=b.doublings,
        tol=Decimal("0.5"),
        at_least=b.at_least,
    )
    if solved is None:
        return SolveResult(knob, baseline, None, None, converged=False)
    solved = solved.quantize(Decimal("0.01"))
    return SolveResult(knob, baseline, solved, _report(goal, b.run(solved)), converged=True)


@dataclass(frozen=True)
class RetirementResult:
    """A retirement date and the success probability it buys.

    `retire_date` is None when no date in the horizon clears the target — a household
    that cannot retire says so, rather than being handed month zero.
    """

    retire_date: date | None
    achieved: float | None
    fi_date: date | None
    """The 4%-rule FI date from the same run, for the UI to show *beside* this one.

    They answer different questions and routinely disagree: `fi_date` is net worth
    crossing `fire_number`, `retire_date` is the simulated date that clears a chosen
    probability with AOW timing, pension unlock and Box 3 drag all in play. Showing one
    while implying the other would be worse than showing neither.
    """
    converged: bool


def retire_at(
    plan: PlanInput,
    month_index: int,
    *,
    person_ids: list[int],
    residual_monthly: Decimal,
) -> PlanInput:
    """`plan` with the named people's income cut to `residual_monthly` at `month_index`.

    Each owned income flow ends in the retirement month, like a `Retire` milestone, so a
    stored IncomeChange firing later cannot bring it back. Its continuation is a
    synthetic copy that starts the month after, with an `IncomeChange` setting it to the
    flow's share of the residual (shares keep their relative sizes, and the amount is
    quoted in the euros of the retirement month). `residual_monthly=0` is full
    retirement and a positive figure is baristaFIRE, one code path rather than two;
    joint flows keep flowing. Nothing to retire from returns the plan untouched rather
    than dividing by zero.

    `PlanInput` carries `start`, not a month list, so the date is arithmetic: no
    projection happens here, which matters because this runs on every bisection step.
    """
    owned = [
        f
        for f in plan.cash_flows
        if f.kind is CashFlowKind.INCOME and f.owner_person_id in person_ids
    ]
    total = sum((f.amount_monthly for f in owned), Decimal(0))
    if total <= 0:
        return plan
    zero = plan.start.year * 12 + (plan.start.month - 1) + month_index
    on_date = date(zero // 12, zero % 12 + 1, 1)
    after = date((zero + 1) // 12, (zero + 1) % 12 + 1, 1)
    factor = residual_monthly / total
    # Synthetic ids: negative, so they exist only inside this candidate plan.
    residual = {
        f.id: f.model_copy(update={"id": -(i + 1), "start_date": after})
        for i, f in enumerate(owned)
    }
    ended = {
        f.id: f.model_copy(update={"end_date": min(f.end_date or on_date, on_date)}) for f in owned
    }
    added = [
        Milestone(
            id=-(i + 1),
            household_id=plan.household.id,
            label=f"retire {f.id}",
            on_date=on_date,
            params=IncomeChange(
                cash_flow_id=residual[f.id].id,
                new_amount_monthly=(f.amount_monthly * factor).quantize(Decimal("0.01")),
            ),
        )
        for i, f in enumerate(owned)
    ]
    flows = [ended.get(f.id, f) for f in plan.cash_flows] + list(residual.values())
    return replace(plan, cash_flows=flows, milestones=[*plan.milestones, *added])


def _retirement_run(
    plan: PlanInput,
    n_placeable: int,
    *,
    person_ids: list[int],
    residual_monthly: Decimal,
    n_runs: int,
    seed: int,
    tax_overrides: TaxOverrides | None,
) -> Callable[[Decimal], Projection]:
    """Run the plan with retirement placed at a (possibly fractional) month index.

    `n_placeable` is `len(calc_months)`, one shorter than the `months` the projection
    reports: index 0 of that list is the opening position, so the last month a milestone
    can actually fire in is `len(months) - 2`. Firing outside the window raises.
    """
    returns = _shared_returns(n_runs, seed)

    def run(month: Decimal) -> Projection:
        idx = max(0, min(n_placeable - 1, int(month)))
        candidate = retire_at(plan, idx, person_ids=person_ids, residual_monthly=residual_monthly)
        return project(
            candidate, n_runs=n_runs, seed=seed, returns=returns, tax_overrides=tax_overrides
        )

    return run


def solve_retirement(
    plan: PlanInput,
    *,
    person_ids: list[int],
    residual_monthly: Decimal,
    probability: float,
    n_runs: int = 1000,
    seed: int = 0,
    tax_overrides: TaxOverrides | None = None,
) -> RetirementResult:
    """Find the earliest month the named people can stop and still clear `probability`.

    They cut income to `residual_monthly` on that date. Bisects the retirement *month*
    over whole months rather than a euro amount. Success is non-decreasing in the
    retirement month — later means more earning months and fewer drawdown months — so
    the months that clear the target are a tail of the horizon and the bisection finds
    where it starts; `test_retiring_later_is_never_worse` pins that rather than trusting
    it. Month 0 is a valid answer, and a tie at the target keeps the earlier month.

    `seed` is fixed across the bisection so success is a deterministic function of the
    month; otherwise Monte Carlo noise would make the bracket wander.
    """
    months = projection_months(plan)
    placeable = len(months) - 1
    run = _retirement_run(
        plan,
        placeable,
        person_ids=person_ids,
        residual_monthly=residual_monthly,
        n_runs=n_runs,
        seed=seed,
        tax_overrides=tax_overrides,
    )
    # `hi` always clears the target and `lo` never does; -1 stands for "before month 0".
    # Only the latest clearing projection is kept: each one holds n_runs full series.
    lo, hi = -1, placeable - 1
    best = run(Decimal(hi))
    if best.success_probability() < probability:
        return RetirementResult(None, None, None, converged=False)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        proj = run(Decimal(mid))
        if proj.success_probability() >= probability:
            hi, best = mid, proj
        else:
            lo = mid
    return RetirementResult(
        retire_date=months[hi],
        achieved=best.success_probability(),
        fi_date=best.fire.fi_dates[0],
        converged=True,
    )


def retirement_success(
    plan: PlanInput,
    *,
    at_month: int,
    person_ids: list[int],
    residual_monthly: Decimal,
    n_runs: int = 1000,
    seed: int = 0,
    tax_overrides: TaxOverrides | None = None,
) -> RetirementResult:
    """Mode 2: the user names the date, this reports the odds. No bisection."""
    months = projection_months(plan)
    placeable = len(months) - 1
    idx = max(0, min(placeable - 1, at_month))
    proj = _retirement_run(
        plan,
        placeable,
        person_ids=person_ids,
        residual_monthly=residual_monthly,
        n_runs=n_runs,
        seed=seed,
        tax_overrides=tax_overrides,
    )(Decimal(idx))
    return RetirementResult(
        retire_date=months[idx],
        achieved=proj.success_probability(),
        fi_date=proj.fire.fi_dates[0],
        converged=True,
    )


TornadoKnob = Literal["return_assumption", "inflation", "swr", "house_appreciation"]

# How far each knob is moved, in absolute rate terms. These are *stated* in the response
# and shown in the UI: a tornado whose bar widths come from undisclosed perturbations is
# decoration, not evidence. SWR moves half as far as the rest because a percentage point
# of withdrawal rate is a much larger change in behaviour than one of inflation.
_TORNADO_DELTAS: dict[TornadoKnob, float] = {
    "return_assumption": 0.01,
    "inflation": 0.01,
    "swr": 0.005,
    "house_appreciation": 0.01,
}

TornadoMetric = Literal["fi_year", "end_net_worth"]

# Named so the branches below read as comparisons against the vocabulary, not as bare
# strings.
_RETURN_KNOB: TornadoKnob = "return_assumption"
_HOUSE_KNOB: TornadoKnob = "house_appreciation"
_BUY_PROPERTY = "buy_property"
_FI_YEAR: TornadoMetric = "fi_year"


@dataclass(frozen=True)
class TornadoRow:
    """One knob's effect: the metric with it moved down, and with it moved up.

    `low`/`high` are the metric, not the knob — a bar runs between them. Either is None
    when FI is not reached in that direction, which the UI must render as "never" rather
    than as a wide finite bar.
    """

    knob: TornadoKnob
    delta: float
    low: float | None
    high: float | None


def _applicable(plan: PlanInput, knob: TornadoKnob) -> bool:
    """Can this plan express the knob at all?

    A knob the household has no exposure to is dropped rather than drawn as a zero-width
    bar: "you own no property, so house appreciation is not a question for you" and "house
    appreciation turns out not to matter to you" are different claims, and only the second
    one is a finding. Inflation and SWR always apply — every plan has spending and a
    withdrawal rate.
    """
    if knob == _RETURN_KNOB:
        return any(a.return_assumption > 0 for a in plan.accounts)
    if knob == _HOUSE_KNOB:
        return any(a.kind is AccountKind.REAL_ESTATE for a in plan.accounts) or any(
            m.params.type == _BUY_PROPERTY for m in plan.milestones
        )
    return True


def _tornado_overrides(plan: PlanInput, knob: TornadoKnob, delta: float) -> ScenarioOverrides:
    """The sparse diff that moves one knob by `delta`.

    Everything goes through `scenarios.apply_scenario` rather than a private plan-mutation
    path, so the tornado and the scenario comparison cannot disagree about what "raise the
    return assumption" means.
    """
    if knob == _RETURN_KNOB:
        # Only the accounts that actually assume a return. Nudging a 0% cash account to
        # 1% would answer a question nobody asked, and would make the cash-heavy
        # household look return-sensitive when it is not.
        return ScenarioOverrides(
            accounts={
                a.id: {"return_assumption": a.return_assumption + delta}
                for a in plan.accounts
                if a.return_assumption > 0
            }
        )
    return ScenarioOverrides(assumptions={knob: getattr(plan.assumptions, knob) + delta})


def tornado_metric(metric: TornadoMetric, proj: Projection) -> float | None:
    """Run 0's FI year, or its end net worth in today's euros.

    Real, not nominal: in nominal euros more inflation inflates the balances it is meant
    to erode, so the inflation bar pointed the wrong way.
    """
    if metric == _FI_YEAR:
        return _fi_year(proj)
    return float(proj.net_worth[0][-1] / proj.inflation_factor[-1])


def tornado(
    plan: PlanInput,
    *,
    metric: TornadoMetric = "fi_year",
    tax_overrides: TaxOverrides | None = None,
) -> list[TornadoRow]:
    """Move one assumption at a time and report how far the metric travels.

    The sensitivity tornado. Its real value is the inverse of what it looks
    like: the knobs whose bars are *narrow* are the ones the household can stop worrying
    about. Rows come back sorted widest first; a knob the plan has no exposure to is
    dropped rather than reported as a zero-width bar (see `_applicable`), because "not
    applicable" and "does not matter" are different answers.

    Deterministic throughout — `n_runs=1`, no Monte Carlo — so it is ~8 projections and
    needs no seed.
    """
    rows: list[TornadoRow] = []
    for knob, delta in _TORNADO_DELTAS.items():
        if not _applicable(plan, knob):
            continue
        overrides = _tornado_overrides(plan, knob, -delta)
        low = _run_with(plan, overrides, tax_overrides)
        high = _run_with(plan, _tornado_overrides(plan, knob, delta), tax_overrides)
        rows.append(
            TornadoRow(
                knob=knob,
                delta=delta,
                low=tornado_metric(metric, low),
                high=tornado_metric(metric, high),
            )
        )
    return sorted(rows, key=_tornado_width, reverse=True)


def _tornado_width(row: TornadoRow) -> float:
    """How far the metric moved.

    A row that reaches "never" in one direction sorts to the top: an assumption that can
    cost you FI entirely is the most sensitive one there is.
    """
    if row.low is None or row.high is None:
        return float("inf")
    return abs(row.high - row.low)


def _run_with(
    plan: PlanInput, overrides: ScenarioOverrides, tax_overrides: TaxOverrides | None
) -> Projection:
    """Project `plan` with one knob moved, keeping the caller's tax overrides."""
    knob_scenario = Scenario(
        id=0, household_id=plan.household.id, name="_tornado", overrides=overrides
    )
    applied, _ = apply_scenario(plan, knob_scenario)
    return project(applied, n_runs=1, tax_overrides=tax_overrides)


_MIN_SWEEP_POINTS = 2


@dataclass(frozen=True)
class SweepPoint:
    """One point on the spending-vs-success curve: a knob level and what it yields."""

    monthly: Decimal
    success: float
    median_end_worth: float


def sweep(
    plan: PlanInput,
    knob: Knob,
    *,
    points: int = 25,
    hi_factor: float = 2.0,
    n_runs: int = 500,
    seed: int = 0,
    tax_overrides: TaxOverrides | None = None,
) -> list[SweepPoint]:
    """Sweep the knob from 0 to `hi_factor` x baseline, reporting success + median end worth.

    The spending-vs-success curve (FIRECalc's best idea). The bisecting
    `solve` answers "what value hits the goal"; this shows the whole shape. A fixed `seed`
    keeps the curve smooth (the same Monte Carlo draws at every point).
    """
    baseline = baseline_monthly(plan, knob)
    if baseline <= 0 or points < _MIN_SWEEP_POINTS:
        return []
    hi = baseline * Decimal(str(hi_factor))
    rows: list[SweepPoint] = []
    returns = _shared_returns(n_runs, seed)
    for i in range(points):
        monthly = (hi * Decimal(i) / Decimal(points - 1)).quantize(Decimal("0.01"))
        proj = project(
            _scaled(plan, knob, monthly, baseline),
            n_runs=n_runs,
            seed=seed,
            returns=returns,
            tax_overrides=tax_overrides,
        )
        rows.append(
            SweepPoint(monthly, proj.success_probability(), float(np.median(proj.net_worth[:, -1])))
        )
    return rows
