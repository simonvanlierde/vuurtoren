"""Metamorphic properties of the engine: two runs compared, not one number pinned.

Each property states how the answer must move when one input moves, which is what a
broken comparison or a stale base breaks. The example tests pin the cases that once
failed; these sweep the space around them.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from test_at_regime import _TO_AT, _TO_NL, _vienna_plan
from test_engine import NO_SWEEP, simple_plan
from test_solve_retirement import _plan as retirement_plan
from vuurtoren.domain import CashFlow, CashFlowKind, ChangeTaxResidence, Milestone
from vuurtoren.engine import PlanInput, project
from vuurtoren.solve import retirement_success, solve_retirement
from vuurtoren.tax.at.config import ATTaxConfig
from vuurtoren.tax.at.income import gross_to_net as at_gross_to_net
from vuurtoren.tax.config import defaults_for as country_defaults
from vuurtoren.tax.nl.box1 import gross_to_net
from vuurtoren.tax.nl.config import NLTaxConfig

# Each example runs one or more 60-year projections, so keep the count low enough for
# the gate; the deadline is off because a projection's time varies with the horizon.
ENGINE = settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])

euros = st.integers(min_value=0, max_value=2_000_000)
spending = st.integers(min_value=500, max_value=6_000)
_NEVER = date.max


def _household(*, equity: int, spend: int, inflation: float = NO_SWEEP.inflation) -> PlanInput:
    """`simple_plan` with an inflation-linked salary and spending and `equity` invested."""
    plan = simple_plan(
        cash_flows=[
            CashFlow(
                id=i,
                household_id=1,
                label=label,
                amount_monthly=Decimal(amount),
                kind=kind,
                inflation_linked=True,
            )
            for i, label, amount, kind in (
                (1, "salary", 5_000, CashFlowKind.INCOME),
                (2, "living", spend, CashFlowKind.EXPENSE),
            )
        ],
        assumptions=replace(NO_SWEEP, inflation=inflation),
    )
    equity_account = plan.accounts[1].model_copy(
        update={"manual_value": Decimal(equity), "cost_basis": Decimal(equity)}
    )
    return replace(plan, accounts=[plan.accounts[0], equity_account])


def _fi(plan: PlanInput) -> date:
    """The deterministic FI date, with "never" ordered after every real date."""
    return project(plan).fire.fi_dates[0] or _NEVER


@ENGINE
@given(equity=euros, spend=spending, low=st.floats(0.0, 0.05), extra=st.floats(0.001, 0.04))
def test_more_inflation_never_brings_fi_forward(
    equity: int, spend: int, low: float, extra: float
) -> None:
    """With salary and spending in real terms, inflation only erodes the nominal return.

    FI compares the pot and the FIRE number in start-month euros; compared nominally, a
    higher price level inflated the pot and left the target behind.
    """
    lower = _fi(_household(equity=equity, spend=spend, inflation=low))
    higher = _fi(_household(equity=equity, spend=spend, inflation=low + extra))
    assert higher >= lower


@ENGINE
@given(equity=euros, more=st.integers(1, 1_000_000), spend=spending)
def test_more_starting_wealth_never_delays_fi(equity: int, more: int, spend: int) -> None:
    """Extra capital on day one can only bring the FI date forward or leave it."""
    assert _fi(_household(equity=equity + more, spend=spend)) <= _fi(
        _household(equity=equity, spend=spend)
    )


@ENGINE
@given(equity=euros, spend=spending, cut=st.integers(1, 2_000))
def test_lower_spending_never_delays_fi(equity: int, spend: int, cut: int) -> None:
    """Spending less lowers the FIRE number and raises the savings, both towards FI."""
    # Kept above zero: with no spending the FIRE number is 0 and the engine reports no FI
    # date at all, a definition rather than a delay.
    leaner = max(1, spend - cut)
    assert _fi(_household(equity=equity, spend=leaner)) <= _fi(
        _household(equity=equity, spend=spend)
    )


def _vienna_household(equity: int, rate: float) -> PlanInput:
    """`_vienna_plan` without its move, with `equity` invested at a `rate` return."""
    plan = _vienna_plan()
    equity_account = plan.accounts[1].model_copy(
        update={"manual_value": Decimal(equity), "return_assumption": rate}
    )
    return replace(plan, accounts=[plan.accounts[0], equity_account], milestones=[])


def _move(milestone_id: int, country: str, on: date, retag: dict[int, str]) -> Milestone:
    return Milestone(
        id=milestone_id,
        household_id=1,
        label=f"Move to {country}",
        on_date=on,
        params=ChangeTaxResidence(country=country, retag=retag),
    )


@ENGINE
@given(
    equity=st.integers(50_000, 2_000_000),
    # Non-negative: a Dutch loss carry belongs to the regime being left and a move drops
    # it on purpose, so a loss year before the trip would rightly change the next year.
    rate=st.floats(0.0, 0.08),
    year=st.integers(2028, 2035),
)
def test_a_one_month_spell_abroad_leaves_the_next_dutch_year_alone(
    equity: int, rate: float, year: int
) -> None:
    """NL -> AT for December, back to NL in January: the year back is taxed as if never away.

    The actual-return base must be re-opened on the return. Carried out of Austria, which
    counts none, it was zero and the first Dutch December taxed the whole portfolio.
    """
    stayed = _vienna_household(equity, rate)
    trip = replace(
        stayed,
        milestones=[
            _move(1, "AT", date(year, 12, 1), _TO_AT),
            _move(2, "NL", date(year + 1, 1, 1), _TO_NL),
        ],
    )
    back = year + 1 - stayed.start.year
    away = float(project(trip).tax_paid["investment_tax"][0, back])
    home = float(project(stayed).tax_paid["investment_tax"][0, back])
    # Not exact: the traveller skipped one Dutch year's tax (about 36% of that year's
    # return) and so holds more; measured at 0.345 x `rate` relative, bounded at 0.4 x.
    assert away == pytest.approx(home, rel=0.4 * rate + 1e-3, abs=1.0)


@ENGINE
@given(
    equity=st.integers(0, 6_000_000),
    spend=st.integers(1_000, 5_000),
)
def test_solve_retirement_returns_month_zero_exactly_when_month_zero_clears(
    equity: int, spend: int
) -> None:
    """Month 0 is the answer whenever retiring today already meets the target.

    The bisection once kept month 0 as its never-clearing low end, so a household that
    could stop today was given a later month — at p = 1, the horizon's last.
    """
    # One deterministic run scores 0 or 1, so every target in (0, 1] is the p = 1 tie.
    probability = 1.0
    plan = retirement_plan(equity=str(equity), spend=str(spend))
    today = retirement_success(
        plan, at_month=0, person_ids=[1], residual_monthly=Decimal(0), n_runs=1
    )
    solved = solve_retirement(
        plan, person_ids=[1], residual_monthly=Decimal(0), probability=probability, n_runs=1
    )
    assert today.achieved is not None
    assert (solved.retire_date == plan.start) == (today.achieved >= probability)


gross_pay = st.decimals(min_value=0, max_value=1_000_000, places=2)
NL_2026 = country_defaults("NL", 2026, expect=NLTaxConfig)
AT_2026 = country_defaults("AT", 2026, expect=ATTaxConfig)


@given(gross=gross_pay, raise_=gross_pay)
def test_dutch_net_pay_never_falls_as_gross_pay_rises(gross: Decimal, raise_: Decimal) -> None:
    """Every Box 1 bracket rate is below 100%, so a raise always leaves some of it."""
    assert gross_to_net(gross + raise_, cfg=NL_2026) >= gross_to_net(gross, cfg=NL_2026)


@given(gross=gross_pay, raise_=gross_pay, sonderzahlungen=st.booleans())
def test_austrian_net_pay_never_falls_as_gross_pay_rises(
    gross: Decimal, raise_: Decimal, *, sonderzahlungen: bool
) -> None:
    """The Austrian chain (social insurance, tariff, 6% on the extra payments) likewise."""
    higher = at_gross_to_net(gross + raise_, cfg=AT_2026, sonderzahlungen=sonderzahlungen)
    assert higher >= at_gross_to_net(gross, cfg=AT_2026, sonderzahlungen=sonderzahlungen)
