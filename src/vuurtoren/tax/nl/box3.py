"""Box 3 — wealth tax.

Regime A (through 2027) taxes a fictional return on net wealth. The tax-free
allowance reduces the *base* proportionally; it is not subtracted from the return.

Every function below taxes one taxpayer, or a pair of fiscal partners as one, over
(n_runs,) float64 arrays. People who are not fiscal partners each pay on their own
share, with their own allowance and debt threshold: `NLTaxRegime` sums those.

One simplification, listed in `regime._LIMITATIONS`: a regime B loss year is taxed as
zero with no loss carried forward.
"""

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from vuurtoren.tax.nl.config import NLTaxConfig


def forfaitair_income_array(
    bank: np.ndarray,
    investments: np.ndarray,
    debt: np.ndarray,
    *,
    fiscal_partners: bool,
    cfg: NLTaxConfig,
) -> np.ndarray:
    """The taxable regime A income ("voordeel uit sparen en beleggen") before the rate.

    Rounded to the cent, as the tax is computed from it. `debt` is the positive amount
    owed.
    """
    n = 2 if fiscal_partners else 1
    eligible_debt = np.maximum(0.0, debt - float(cfg.box3_debt_threshold_per_person) * n)
    grondslag = bank + investments - eligible_debt
    allowance = float(cfg.box3_allowance_per_person) * n
    rendement = (
        bank * float(cfg.box3_forfait_bank)
        + investments * float(cfg.box3_forfait_investments)
        - eligible_debt * float(cfg.box3_forfait_debt)
    )
    # The proportional-allowance step. `where` on the divisor keeps
    # a zero grondslag out of the division; the outer `where` zeroes those runs anyway.
    aandeel = (grondslag - allowance) / np.where(grondslag > 0.0, grondslag, 1.0)
    return np.where(grondslag > allowance, np.round(np.maximum(0.0, rendement * aandeel), 2), 0.0)


def box3_tax_array(
    bank: np.ndarray,
    investments: np.ndarray,
    debt: np.ndarray,
    actual_return: np.ndarray | None,
    *,
    year: int,
    fiscal_partners: bool,
    cfg: NLTaxConfig,
    elect: bool = True,
) -> np.ndarray:
    """Box 3 tax for `year`, regime A or B by `cfg.regime_switch_year`.

    `debt` is the positive amount owed. `actual_return` is the proven return, or None
    when there is none: regime A then stays forfaitair, and regime B refuses to run.
    """
    for name, v in (("bank", bank), ("investments", investments), ("debt", debt)):
        if np.any(v < 0):
            msg = f"{name} must not be negative"
            raise ValueError(msg)
    if year >= cfg.regime_switch_year:
        # Regime B, Wet werkelijk rendement: the actual return (realised income plus
        # unrealised value change) taxed annually above a per-person tax-free income. The
        # vermogenswinst path for real estate is not implemented: a primary residence sits
        # in Box 1 under both regimes, so there is no Box 3 real estate to defer.
        if actual_return is None:
            msg = "regime B requires actual_return"
            raise ValueError(msg)
        n = 2 if fiscal_partners else 1
        taxable = np.maximum(0.0, actual_return - float(cfg.wwr_allowance_per_person) * n)
        return np.round(taxable * float(cfg.wwr_rate), 2)

    income = forfaitair_income_array(
        bank, investments, debt, fiscal_partners=fiscal_partners, cfg=cfg
    )
    # The tegenbewijs (Wet tegenbewijsregeling): a proven actual return below the
    # forfaitair income is taxed instead. `elect=False` is the "what if it were repealed"
    # lever.
    if elect and actual_return is not None:
        income = np.minimum(income, np.maximum(0.0, actual_return))
    return np.round(income * float(cfg.box3_rate), 2)
