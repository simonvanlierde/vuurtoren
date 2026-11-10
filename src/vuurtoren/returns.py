"""Monthly-return providers: the fixed projection and the Monte Carlo and backtest modes.

A provider maps (account, month, n_runs) to a monthly return; `engine.project` takes one.
"""

from collections.abc import Callable

import numpy as np

from vuurtoren.domain import Account, AccountKind
from vuurtoren.returns_data import HISTORICAL_ANNUAL_RETURNS

ReturnsProvider = Callable[[Account, int, int], "np.ndarray | float"]
"""(account, month_index, n_runs) -> monthly return, shape (n_runs,) or a scalar.

A scalar is broadcast across runs. The Monte Carlo provider returns the full array;
`fixed_returns` returns a scalar because the value is the same in every run.
"""


def fixed_returns(account: Account, _month: int, _n_runs: int) -> np.ndarray | float:
    """Deterministic monthly return from the account's nominal annual assumption.

    `return_assumption` is a *nominal* annual rate, so the monthly rate is
    annual / 12 and twelve of them compound to slightly more than the annual figure
    (6% -> 6.17%). That is what "nominal" means, and the mortgage side uses the same
    convention because a lender's annuity schedule does. Inflation and house
    appreciation are not nominal rates and deliberately do not — see `project`.

    Returns a scalar: numpy broadcasts it against the (n_runs,) balances, and
    materialising the constant per account per month costs ~20% of a deterministic run.
    """
    return account.return_assumption / 12


def gaussian_returns(seed: int | None) -> ReturnsProvider:
    """Monte Carlo returns from one Gaussian shock per (month, account kind).

    The shock is shared by every account of that kind and scaled by the account's own
    mean and volatility.

    The household's equity trackers are near-perfectly correlated —
    independent draws would understate risk badly and quietly flatter every scenario,
    so one shock drives all accounts of a kind. Cross-kind correlation is not
    modelled. `default_rng(seed)`, so a stored seed reproduces every chart.
    """
    rng = np.random.default_rng(seed)
    shocks: dict[tuple[int, AccountKind], np.ndarray] = {}

    def provider(account: Account, month: int, n_runs: int) -> np.ndarray | float:
        mu = account.return_assumption / 12
        sigma = account.volatility_assumption / np.sqrt(12.0)
        if sigma == 0.0:
            return mu
        key = (month, account.kind)
        if key not in shocks:
            shocks[key] = rng.standard_normal(n_runs)
        return mu + sigma * shocks[key]

    return provider


BLOCK_YEARS = 5
"""Bootstrap block length, in years. Each run chains random 5-year slices of the
historical series so a multi-year drawdown (1973-74, 2000-02, 2008) survives intact
inside a block — the sequence risk Gaussian draws destroy. A module constant, not a
parameter: the dataset is fixed and so is the natural block length for it."""


def _draw_block(rng: np.random.Generator, n_data_years: int, n_runs: int) -> np.ndarray:
    """(n_runs,) random start indices for one contiguous BLOCK_YEARS slice."""
    return rng.integers(0, n_data_years - BLOCK_YEARS + 1, size=n_runs)


def historical_returns(seed: int | None) -> ReturnsProvider:
    """Monte Carlo returns from a block bootstrap of real global-equity years.

    Every EQUITY account is driven by one bootstrapped series per run, because
    both people hold global trackers, so independent draws
    would understate risk. The series *is* the equity return assumption here; each
    account's own `return_assumption`/`volatility_assumption` are ignored (the dataset,
    `returns_data.HISTORICAL_ANNUAL_RETURNS`, carries both mean and volatility). Every
    other account kind — and any zero-volatility account — keeps its deterministic
    `return_assumption / 12`, exactly as in the fixed projection.

    Each drawn calendar year contributes twelve equal monthly returns via
    `(1 + annual) ** (1/12) - 1`: a realised annual return is a year-on-year figure, so
    it converts like inflation, not like the nominal `return_assumption` (the
    two-conversions rule in CONTRIBUTING.md). Blocks are drawn lazily as the projection
    walks months in order, so the (month, run) grid is filled without a Python loop over
    runs.
    `default_rng(seed)`, so a stored seed reproduces every chart.
    """
    rng = np.random.default_rng(seed)
    series = np.asarray(HISTORICAL_ANNUAL_RETURNS, dtype=float)
    n_data_years = len(series)
    block_starts: dict[int, np.ndarray] = {}
    monthly_by_year: dict[int, np.ndarray] = {}

    def _monthly_for_year(year_idx: int, n_runs: int) -> np.ndarray:
        if year_idx not in monthly_by_year:
            block, offset = divmod(year_idx, BLOCK_YEARS)
            if block not in block_starts:
                block_starts[block] = _draw_block(rng, n_data_years, n_runs)
            annual = series[block_starts[block] + offset]
            monthly_by_year[year_idx] = (1.0 + annual) ** (1.0 / 12.0) - 1.0
        return monthly_by_year[year_idx]

    def provider(account: Account, month: int, n_runs: int) -> np.ndarray | float:
        if account.kind is not AccountKind.EQUITY:
            return account.return_assumption / 12.0
        return _monthly_for_year(month // 12, n_runs)

    return provider


def sequential_returns() -> ReturnsProvider:
    """One run per real start year: the sequential backtest.

    Run `r` lives through the dataset starting at `HISTORICAL_ANNUAL_RETURNS[r]`, so
    `n_runs` is the dataset length and each run has a name — 1970, 1971, ... 2024, per
    `returns_data.START_YEARS`. That is a different and blunter claim than the fan
    chart's percentiles: "every start year since 1970 works except 2000" is a fact
    about history, not a sample from a distribution. Sequence-of-returns risk is the
    thing this shows that a Gaussian draw structurally cannot.

    No rng and no seed: the mode is deterministic by construction, so a chart
    reproduces without one. `project(seed=...)` only feeds the *default* provider, so
    passing None alongside this one is correct rather than a lapse.

    **The series wraps.** A 60-year projection outruns 55 years of data, so year k of
    run r is dataset year `(r + k) % 55` — 1970 follows 2024. That puts exactly one
    artificial seam in each run long enough to reach it, and keeps real sequence shape
    everywhere else; clipping to the last year instead would fabricate a decade of
    identical returns. The UI says so out loud, alongside the caveat that ~55
    overlapping start windows are not 55 independent samples — do not quote a success
    rate off them without it.

    Shares `historical_returns`' other three rules: only EQUITY is driven by the
    dataset (every other kind keeps its deterministic `return_assumption / 12`), every
    EQUITY account gets the same series per run (both people hold global trackers, so
    independent draws would understate risk), and a drawn calendar year contributes
    twelve equal monthly returns via `(1 + annual) ** (1/12) - 1` — a realised annual
    return is a year-on-year figure, so it converts like inflation, not like the
    nominal `return_assumption` (the two-conversions rule in CONTRIBUTING.md).
    """
    series = np.asarray(HISTORICAL_ANNUAL_RETURNS, dtype=float)
    n_data_years = len(series)
    # Keyed by (year, n_runs), not year alone: the provider is called with whatever
    # n_runs the projection is running, and a cached row of the wrong width would
    # broadcast silently rather than fail.
    monthly_by_year: dict[tuple[int, int], np.ndarray] = {}

    def _monthly_for_year(year_idx: int, n_runs: int) -> np.ndarray:
        key = (year_idx, n_runs)
        if key not in monthly_by_year:
            offsets = (np.arange(n_runs) + year_idx) % n_data_years
            monthly_by_year[key] = (1.0 + series[offsets]) ** (1.0 / 12.0) - 1.0
        return monthly_by_year[key]

    def provider(account: Account, month: int, n_runs: int) -> np.ndarray | float:
        if account.kind is not AccountKind.EQUITY:
            return account.return_assumption / 12.0
        return _monthly_for_year(month // 12, n_runs)

    return provider
