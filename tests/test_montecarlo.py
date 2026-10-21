"""The Gaussian returns provider and the Monte Carlo invariants."""

from decimal import Decimal

import numpy as np
import pytest

from test_engine import simple_plan
from vuurtoren.domain import Account, AccountKind, CashFlow, CashFlowKind, Household
from vuurtoren.engine import (
    BLOCK_YEARS,
    Assumptions,
    PlanInput,
    _bootstrap_year_indices,
    gaussian_returns,
    historical_returns,
    project,
    sequential_returns,
)
from vuurtoren.returns_data import FIRST_YEAR, HISTORICAL_ANNUAL_RETURNS, START_YEARS


def volatile_plan(
    *, equity: str = "100000", volatility: float = 0.10, life: int = 40, **kw: object
) -> PlanInput:
    """A short (born 1990, life expectancy `life`) plan with one volatile equity account.

    Ten-ish year horizon by default (-> 2036): short enough that the median-vs-mean
    gap of compounding stays inside loose tolerances.
    """
    household = Household(id=1, name="T", fiscal_partners=False, life_expectancy_age=life)
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
            name="Equity",
            kind=AccountKind.EQUITY,
            tax_treatment="nl.none",
            manual_value=Decimal(equity),
            return_assumption=0.06,
            volatility_assumption=volatility,
        ),
    ]
    return simple_plan(
        household=household,
        accounts=accounts,
        assumptions=Assumptions(cash_buffer_mode="off"),
        **kw,
    )


def _acct(account_id: int, kind: AccountKind, mu: float, sigma: float) -> Account:
    return Account(
        id=account_id,
        household_id=1,
        name=f"a{account_id}",
        kind=kind,
        tax_treatment="nl.none",
        return_assumption=mu,
        volatility_assumption=sigma,
    )


# --- the provider itself ---


def test_accounts_of_one_kind_share_a_single_return_series() -> None:
    """Two EQUITY accounts draw one shared shock per month, scaled by each one's mu/sigma.

    Both people hold global equity trackers — near-perfectly correlated.
    Independent draws would understate risk badly.
    """
    provider = gaussian_returns(seed=1)
    a = provider(_acct(1, AccountKind.EQUITY, 0.06, 0.15), 0, 1000)
    b = provider(_acct(2, AccountKind.EQUITY, 0.05, 0.20), 0, 1000)
    z_a = (a - 0.06 / 12) / (0.15 / np.sqrt(12))
    z_b = (b - 0.05 / 12) / (0.20 / np.sqrt(12))
    assert np.allclose(z_a, z_b)


def test_different_kinds_draw_independent_series() -> None:
    """EQUITY and BOND accounts draw independent shock series, not one shared shock."""
    provider = gaussian_returns(seed=1)
    equity = provider(_acct(1, AccountKind.EQUITY, 0.06, 0.15), 0, 1000)
    bond = provider(_acct(2, AccountKind.BOND, 0.06, 0.15), 0, 1000)
    assert not np.allclose(equity, bond)


def test_zero_volatility_is_the_deterministic_rate() -> None:
    """An account with volatility_assumption=0.0 always draws its nominal monthly rate."""
    provider = gaussian_returns(seed=1)
    assert provider(_acct(1, AccountKind.CASH, 0.012, 0.0), 5, 100) == 0.012 / 12


# --- invariants through project() ---


def test_a_fixed_seed_reproduces_the_projection_exactly() -> None:
    """The same seed reproduces byte-identical net worth across two projections."""
    a = project(volatile_plan(), n_runs=64, seed=7)
    b = project(volatile_plan(), n_runs=64, seed=7)
    assert np.array_equal(a.net_worth, b.net_worth)


def test_different_seeds_produce_different_runs() -> None:
    """Different seeds produce different net worth arrays for the same plan."""
    a = project(volatile_plan(), n_runs=64, seed=7)
    b = project(volatile_plan(), n_runs=64, seed=8)
    assert not np.array_equal(a.net_worth, b.net_worth)


def test_runs_spread_without_an_explicit_provider() -> None:
    """n_runs > 1 defaults to the Gaussian provider, not to 10,000 silently identical runs."""
    p = project(volatile_plan(), n_runs=16, seed=3)
    assert float(np.std(p.net_worth[:, -1])) > 0.0


def test_the_mean_of_runs_tracks_the_deterministic_result() -> None:
    """The mean final net worth across many stochastic runs tracks the deterministic result."""
    mc = project(volatile_plan(), n_runs=4000, seed=3)
    det = project(volatile_plan())
    mean_final = float(np.mean(mc.net_worth[:, -1]))
    det_final = float(det.net_worth[0, -1])
    assert mean_final == pytest.approx(det_final, rel=0.05)


def test_the_median_run_is_near_and_below_the_mean() -> None:
    """The median run's final net worth is near the deterministic result and below the mean.

    Compounding volatile returns is right-skewed.
    """
    mc = project(volatile_plan(), n_runs=4000, seed=3)
    det = project(volatile_plan())
    p50 = float(np.percentile(mc.net_worth[:, -1], 50))
    assert p50 == pytest.approx(float(det.net_worth[0, -1]), rel=0.10)
    assert p50 <= float(np.mean(mc.net_worth[:, -1]))


def _success_rate(equity: str) -> float:
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
    plan = volatile_plan(equity=equity, volatility=0.15, cash_flows=flows)
    # The default buffer must stay on here: it is what sells equity to fund the
    # spending, so "success" means the portfolio lasted.
    plan = simple_plan(
        household=plan.household,
        accounts=plan.accounts,
        cash_flows=flows,
    )
    p = project(plan, n_runs=400, seed=11)
    return sum(1 for d in p.cash_shortfall if d is None) / len(p.cash_shortfall)


def test_success_probability_is_monotonic_in_starting_wealth() -> None:
    """A richer starting portfolio has a strictly higher Monte Carlo success rate."""
    poor, rich = _success_rate("150000"), _success_rate("500000")
    assert rich > poor


# --- the historical bootstrap ---


def test_the_block_sampler_draws_contiguous_slices() -> None:
    """Every BLOCK_YEARS window is a run of consecutive dataset years, never a reshuffle.

    Sequence risk lives *inside* a block: the index step within a window must be
    exactly 1.
    """
    rng = np.random.default_rng(0)
    n_data = len(HISTORICAL_ANNUAL_RETURNS)
    idx = _bootstrap_year_indices(rng, n_data, n_proj_years=40, n_runs=200)
    assert idx.shape == (200, 40)
    assert idx.min() >= 0
    assert idx.max() < n_data
    for block in range(40 // BLOCK_YEARS):
        window = idx[:, block * BLOCK_YEARS : (block + 1) * BLOCK_YEARS]
        assert np.all(np.diff(window, axis=1) == 1)


def test_historical_equity_shares_one_series_regardless_of_account_assumptions() -> None:
    """Every EQUITY account gets the same drawn historical series per run.

    Its own mu/sigma are ignored — the dataset is the return assumption.
    """
    provider = historical_returns(seed=1)
    a = provider(_acct(1, AccountKind.EQUITY, 0.06, 0.15), 0, 1000)
    b = provider(_acct(2, AccountKind.EQUITY, 0.03, 0.40), 0, 1000)
    assert np.array_equal(a, b)


def test_historical_non_equity_stays_deterministic() -> None:
    """Non-EQUITY accounts stay at their deterministic rate under the historical provider too."""
    provider = historical_returns(seed=1)
    assert provider(_acct(1, AccountKind.CASH, 0.012, 0.0), 5, 100) == 0.012 / 12
    bond = provider(_acct(2, AccountKind.BOND, 0.03, 0.20), 0, 100)
    assert bond == 0.03 / 12


def test_historical_twelve_months_of_a_year_are_one_realised_return() -> None:
    """A drawn calendar year contributes twelve equal monthly returns, not independent shocks.

    Via the geometric conversion, so a year is a year.
    """
    provider = historical_returns(seed=2)
    equity = _acct(1, AccountKind.EQUITY, 0.06, 0.15)
    jan = provider(equity, 0, 500)
    dec = provider(equity, 11, 500)
    assert np.array_equal(jan, dec)
    # And the year rolls over: month 12 is a different (possibly new-block) year.
    next_year = provider(equity, 12, 500)
    assert not np.array_equal(jan, next_year)
    # Every element is a real dataset year run through (1+r)**(1/12)-1.
    expected = (1.0 + np.asarray(HISTORICAL_ANNUAL_RETURNS)) ** (1 / 12) - 1
    assert np.all(np.isin(np.round(jan, 12), np.round(expected, 12)))


def test_historical_fixed_seed_reproduces_the_projection() -> None:
    """The same seed reproduces byte-identical net worth under the historical provider too."""
    a = project(volatile_plan(), n_runs=64, seed=7, returns=historical_returns(7))
    b = project(volatile_plan(), n_runs=64, seed=7, returns=historical_returns(7))
    assert np.array_equal(a.net_worth, b.net_worth)


def test_historical_equity_spreads_while_cash_stays_flat() -> None:
    """Through project(), equity fans out across runs while a zero-return cash account stays flat.

    The cash account has no flows and return_assumption=0, so it is constant in
    every run and month; equity spreads via the bootstrapped sequences.
    """
    p = project(volatile_plan(), n_runs=48, seed=5, returns=historical_returns(5))
    cash = p.components["cash"]
    assert np.allclose(cash, 10_000.0)
    assert float(np.std(p.components["liquid_investments"][:, -1])) > 0.0


# --- the sequential backtest: one run per real start year ---


def test_sequential_run_r_is_start_year_r() -> None:
    """Run r's first year is dataset year r: the runs *are* the start years.

    That is the whole claim of the mode — run 0 is 1970, run 30 is 2000.
    """
    provider = sequential_returns()
    equity = _acct(1, AccountKind.EQUITY, 0.06, 0.15)
    n = len(HISTORICAL_ANNUAL_RETURNS)
    jan = provider(equity, 0, n)
    expected = (1.0 + np.asarray(HISTORICAL_ANNUAL_RETURNS)) ** (1 / 12) - 1
    assert np.allclose(jan, expected)


def test_sequential_walks_the_series_forward_and_wraps() -> None:
    """Year k of run r is dataset year (r + k) mod 55 — real order, one seam per run."""
    provider = sequential_returns()
    equity = _acct(1, AccountKind.EQUITY, 0.06, 0.15)
    n = len(HISTORICAL_ANNUAL_RETURNS)
    annual = np.asarray(HISTORICAL_ANNUAL_RETURNS)
    for year in (1, 7, 54, 55, 60):
        got = provider(equity, year * 12, n)
        want = (1.0 + np.roll(annual, -year)) ** (1 / 12) - 1
        assert np.allclose(got, want), f"year {year}"


def test_sequential_twelve_months_of_a_year_are_one_realised_return() -> None:
    """A calendar year is twelve equal monthly returns, geometrically converted."""
    provider = sequential_returns()
    equity = _acct(1, AccountKind.EQUITY, 0.06, 0.15)
    n = len(HISTORICAL_ANNUAL_RETURNS)
    jan, dec = provider(equity, 0, n), provider(equity, 11, n)
    assert np.array_equal(jan, dec)
    assert not np.array_equal(jan, provider(equity, 12, n))


def test_sequential_equity_shares_one_series_regardless_of_account_assumptions() -> None:
    """Every EQUITY account gets the same series per run; its own mu/sigma are ignored."""
    provider = sequential_returns()
    n = len(HISTORICAL_ANNUAL_RETURNS)
    a = provider(_acct(1, AccountKind.EQUITY, 0.06, 0.15), 0, n)
    b = provider(_acct(2, AccountKind.EQUITY, 0.03, 0.40), 0, n)
    assert np.array_equal(a, b)


def test_sequential_non_equity_stays_deterministic() -> None:
    """Non-EQUITY accounts keep their own rate under the sequential provider too."""
    provider = sequential_returns()
    assert provider(_acct(1, AccountKind.CASH, 0.012, 0.0), 5, 55) == 0.012 / 12
    assert provider(_acct(2, AccountKind.BOND, 0.03, 0.20), 0, 55) == 0.03 / 12


def test_sequential_needs_no_seed_to_reproduce() -> None:
    """No rng at all: two runs of the same plan are byte-identical without a seed."""
    n = len(HISTORICAL_ANNUAL_RETURNS)
    a = project(volatile_plan(), n_runs=n, returns=sequential_returns())
    b = project(volatile_plan(), n_runs=n, returns=sequential_returns())
    assert np.array_equal(a.net_worth, b.net_worth)
    # And the runs genuinely differ from one another — 55 start years, 55 outcomes.
    assert float(np.std(a.components["liquid_investments"][:, -1])) > 0.0


def test_start_years_label_every_dataset_index() -> None:
    """START_YEARS is the calendar label for each index — the run r <-> year map."""
    assert len(START_YEARS) == len(HISTORICAL_ANNUAL_RETURNS)
    assert START_YEARS[0] == FIRST_YEAR
    assert START_YEARS[-1] == FIRST_YEAR + len(HISTORICAL_ANNUAL_RETURNS) - 1
    assert list(START_YEARS) == sorted(START_YEARS)
