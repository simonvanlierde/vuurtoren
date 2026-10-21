"""US federal tax on ordinary income, and the foreign earned income exclusion.

Seven bands, like Austria's, but `(n_runs,)` numpy throughout rather than scalar
`Decimal`: this feeds a `CitizenshipOverlay`, which sits inside the engine's array world
(invariant #6). `tax/at/income.py` is the shape to read for the ladder; the arithmetic
here is the branch-free array form of it.

**The FEIE is an election, and this module always takes it.** Section 911 lets a US person
abroad exclude earned income up to `feie_limit`, at the price of barring the foreign tax
credit on the same income (§ 911(d)(6)). Whether that beats claiming the credit on
everything depends on the residence country's rate and on how much unused credit the
household is banking, and the honest answer is often *no* in a high-tax country like the
Netherlands. Solving for the better of the two per year is a real optimisation and is not
modelled — the app takes the exclusion first and credits the rest.

Which way that bends the answer: always-FEIE can never beat the optimal election, so the
US tax computed here is at or above what a well-advised filer would pay, and the FIRE
date is at worst pessimistic. It is never the other way round. The place it bites hardest
is the credit carryforward, which the exclusion quietly shrinks.

**Section 911(f) is modelled**, not skipped. The exclusion lowers the *base*, never the
bracket: income above the limit is taxed at the rate it would have met had nothing been
excluded. Ignoring that would tax a $183,000 salary as if it were a $50,000 one.
"""

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from vuurtoren.domain import FilingStatus
    from vuurtoren.tax.us.config import USTaxConfig

_BANDS = 7
"""Ordinary bands, § 1(j)(2). Six thresholds plus a top band with no upper bound."""


def _ladder(cfg: USTaxConfig, status: FilingStatus) -> list[tuple[float, float]]:
    """The schedule as (upper bound, marginal rate), lowest band first.

    The top band's bound is `inf` rather than a large finite number: `np.clip` handles it
    exactly, so nothing has to pick a ceiling no income reaches.
    """
    tops = [
        float(cfg.by_filing_status(f"ordinary_bracket_{n}_to", status)) for n in range(1, _BANDS)
    ]
    rates = [float(getattr(cfg, f"ordinary_rate_{n}")) for n in range(1, _BANDS + 1)]
    return list(zip([*tops, np.inf], rates, strict=True))


def tax_on_slice(
    bands: list[tuple[float, float]], *, start: np.ndarray | float, end: np.ndarray
) -> np.ndarray:
    """Marginal-rate tax on the income lying between `start` and `end`, per run.

    Branch-free: `clip(x, lower, upper)` is `lower` below a band, `upper` above it, and
    `x` inside it, so each band contributes exactly the overlap between itself and the
    slice — zero when they do not overlap. Every run takes the same path; no `where`.

    A slice rather than a plain total because both federal charges need it. Ordinary tax
    is the slice from zero. The preferential rates in `investment.py` are the slice from
    the top of ordinary income upwards, which is what "capital gains stack on top of
    ordinary income" means arithmetically — and reading those thresholds against the gain
    alone instead would leave nearly every gain in the app untaxed.
    """
    tax = np.zeros_like(end)
    lower = 0.0
    for upper, rate in bands:
        tax += (np.clip(end, lower, upper) - np.clip(start, lower, upper)) * rate
        lower = upper
    return tax


def bracket_tax(income: np.ndarray, *, status: FilingStatus, cfg: USTaxConfig) -> np.ndarray:
    """Ordinary tax on a taxable base, per run. A negative base is zero, not a refund."""
    return tax_on_slice(_ladder(cfg, status), start=0.0, end=np.maximum(0.0, income))


def excluded_earned_income(earned: np.ndarray, *, cfg: USTaxConfig) -> np.ndarray:
    """The part of earned income the § 911 election keeps out of the US base.

    Earned income only — a salary, not a dividend. The limit is per person and does not
    vary by filing status.
    """
    return np.clip(earned, 0.0, float(cfg.feie_limit))


def taxable_income(
    earned: np.ndarray,
    other_ordinary: np.ndarray,
    *,
    status: FilingStatus,
    cfg: USTaxConfig,
) -> np.ndarray:
    """Ordinary income after the exclusion and the standard deduction, floored at zero.

    Itemised deductions are not modelled: for an expatriate whose largest itemisable
    expense is usually foreign tax — which this household claims as a credit instead, and
    cannot do both — the standard deduction is the normal answer. Where it is not, this
    overstates the base and so the tax.
    """
    excluded = excluded_earned_income(earned, cfg=cfg)
    deduction = float(cfg.by_filing_status("standard_deduction", status))
    return np.maximum(0.0, earned + other_ordinary - excluded - deduction)


def unused_deduction(
    earned: np.ndarray,
    other_ordinary: np.ndarray,
    *,
    status: FilingStatus,
    cfg: USTaxConfig,
) -> np.ndarray:
    """The part of the standard deduction ordinary income did not absorb.

    It does not go to waste: the deduction reduces *taxable income*, and long-term gains
    and qualified dividends are part of that. A retiree living entirely off qualified
    dividends has no ordinary income at all, and without this would be taxed from the
    first dollar of the preferential ladder — losing the deduction outright.

    Returned rather than applied here because the preferential base lives in
    `investment.py`, and `taxable_income` above must keep meaning *ordinary* taxable
    income: that is what the preferential thresholds are measured from.
    """
    excluded = excluded_earned_income(earned, cfg=cfg)
    deduction = float(cfg.by_filing_status("standard_deduction", status))
    return np.maximum(0.0, deduction - np.maximum(0.0, earned + other_ordinary - excluded))


def ordinary_tax(
    taxable: np.ndarray,
    *,
    excluded: np.ndarray,
    status: FilingStatus,
    cfg: USTaxConfig,
) -> np.ndarray:
    """Federal ordinary tax, with the § 911(f) stacking rule applied.

    The statute's own arithmetic: the tax on the base *including* the excluded amount,
    less the tax the excluded amount alone would have borne. With nothing excluded it
    collapses to `bracket_tax`, so there is no second code path for the non-expat case.
    """
    return bracket_tax(taxable + excluded, status=status, cfg=cfg) - bracket_tax(
        excluded, status=status, cfg=cfg
    )
