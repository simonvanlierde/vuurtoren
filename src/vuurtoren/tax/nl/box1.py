"""Box 1 — owner-occupied home: hypotheekrenteaftrek, eigenwoningforfait.

Annuity/amortisation maths is country-neutral and lives in `vuurtoren.mortgage`.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from vuurtoren.tax.nl.config import NLTaxConfig

_CENTS = Decimal("0.01")
_ZERO = Decimal(0)

# Wet Hillen phase-out baseline year. cfg.year is the query year (defaults_for stamps it
# per call), not a fixed anchor, so the baseline the phase-out counts from lives here
# rather than in cfg.
_HILLEN_BASE_YEAR = 2026


def _round(x: Decimal) -> Decimal:
    return x.quantize(_CENTS, rounding=ROUND_HALF_UP)


def gross_to_net(gross_annual: Decimal, *, cfg: NLTaxConfig) -> Decimal:
    """Net annual wage income after Box 1 tax, below AOW age.

    Progressive over the three brackets, minus the algemene heffingskorting and
    arbeidskorting at their MAXIMA — the income-dependent phase-outs are not modelled,
    so for incomes past the afbouw points this overstates net income by up to the
    phased-out credit. Kortingen can reduce the tax to zero, never below (no refund).
    """
    if gross_annual <= _ZERO:
        return _ZERO
    tax = (
        min(gross_annual, cfg.box1_bracket_1_to) * cfg.box1_rate_1
        + max(_ZERO, min(gross_annual, cfg.box1_bracket_2_to) - cfg.box1_bracket_1_to)
        * cfg.box1_rate_2
        + max(_ZERO, gross_annual - cfg.box1_bracket_2_to) * cfg.box1_rate_3
    )
    tax = max(_ZERO, tax - cfg.general_credit_max - cfg.labour_credit_max)
    return _round(gross_annual - tax)


def net_housing_tax_effect_array(
    interest_paid_year: np.ndarray, woz: np.ndarray, *, year: int, cfg: NLTaxConfig
) -> np.ndarray:
    """Signed annual Box 1 effect of owning the home, over (n_runs,) arrays.

    Positive is a net deduction (interest exceeds the eigenwoningforfait). Negative is
    net tax owed: once the forfait exceeds interest paid, the excess is taxable income,
    reduced by the phasing-out Wet Hillen relief (aftrek wegens geen of geringe
    eigenwoningschuld). The forfait has two tiers; the upper one is the villatax. Runs
    without a home (woz <= 0) return 0.
    """
    ewf = np.round(
        np.minimum(np.maximum(woz, 0.0), float(cfg.ewf_threshold)) * float(cfg.ewf_rate)
        + np.maximum(0.0, woz - float(cfg.ewf_threshold)) * float(cfg.ewf_high_rate),
        2,
    )
    deduction = np.round((interest_paid_year - ewf) * float(cfg.hra_max_rate), 2)
    hillen = max(
        0.0,
        float(cfg.hillen_rate) - (year - _HILLEN_BASE_YEAR) * float(cfg.hillen_phaseout_per_year),
    )
    owed = -np.round((ewf - interest_paid_year) * (1.0 - hillen) * float(cfg.hra_max_rate), 2)
    return np.where(woz > 0.0, np.where(interest_paid_year >= ewf, deduction, owed), 0.0)


def pension_withdrawal_tax_array(amount: np.ndarray, cfg: NLTaxConfig) -> np.ndarray:
    """Box 1 income tax on taking `amount` out of a lijfrente, over (n_runs,) arrays.

    A flat marginal rate. A uitkering lands on top of AOW and whatever else the
    household receives, so the marginal bracket is the honest single number; running the
    progressive schedule from zero on the withdrawal alone would understate it badly.

    A negative amount is a deposit, not a withdrawal, and is never taxed here.
    """
    return np.round(np.maximum(amount, 0.0) * float(cfg.pension_withdrawal_rate), 2)
