"""US federal tax on investment income: preferential rates, and the NIIT on top.

Two charges that look similar and are not. The preferential rates *replace* the ordinary
ones for long-term gains and qualified dividends; the net investment income tax is a
second charge levied on the same income under a different chapter, so a dollar of gain
above the threshold pays both.

**The preferential thresholds read total taxable income, not the gain.** A gain stacks on
top of ordinary income and is taxed by where it lands, so the same $10,000 gain is
untaxed for a low earner and taxed at 15 % for someone whose salary already fills the
zero band. Reading the threshold against the gain alone — the natural mistake — would
leave nearly every gain in this app untaxed. That is why the ladder is applied to a
*slice* (`income.tax_on_slice`) rather than to a total.

**The NIIT is charged uncredited, and that is a decision, not an oversight.** § 1411 sits
in chapter 2A, outside the § 901 foreign tax credit. Two Court of Federal Claims
decisions read the NL-US treaty's relief article as an independent grant of credit
anyway — *Christensen*, 168 Fed. Cl. 263 (2023) and *Bruyea*, 174 Fed. Cl. 238 (2024) —
but Treasury appealed both and the Federal Circuit consolidated them in April 2025,
undecided as of 2026-07-28. Charging it uncredited **overstates** US tax if the taxpayers
win, so the app takes the conservative side. `docs/decisions.md` carries the full
reasoning and the sources.

**Not modelled:** the capital loss carryforward and the $3,000 ordinary-income offset. A
loss year charges nothing here and banks nothing, which overstates tax in the years after
a loss. The engine's per-account cost basis is where a carryforward would come from.
"""

from typing import TYPE_CHECKING

import numpy as np

from vuurtoren.tax.us.federal.income import tax_on_slice

if TYPE_CHECKING:
    from vuurtoren.domain import FilingStatus
    from vuurtoren.tax.us.config import USTaxConfig


def _preferential_ladder(cfg: USTaxConfig, status: FilingStatus) -> list[tuple[float, float]]:
    """The 0 / 15 / 20 schedule as (upper bound of total taxable income, rate)."""
    return [
        (float(cfg.by_filing_status("ltcg_zero_rate_top", status)), float(cfg.ltcg_rate_1)),
        (float(cfg.by_filing_status("ltcg_fifteen_rate_top", status)), float(cfg.ltcg_rate_2)),
        (np.inf, float(cfg.ltcg_rate_3)),
    ]


def preferential_tax(
    preferential_income: np.ndarray,
    *,
    ordinary_taxable: np.ndarray,
    status: FilingStatus,
    cfg: USTaxConfig,
) -> np.ndarray:
    """Tax on long-term gains and qualified dividends, stacked on ordinary income.

    `preferential_income` is the net long-term gain plus qualified dividends — the two
    share one schedule (§ 1(h)), so they are one argument rather than two. Qualification
    is assumed: a US-domiciled fund's dividends and a holding sold after a year both
    qualify, and treating a non-qualified dividend as qualified would understate the tax.
    That is the caller's classification to get right, not this function's.

    A net loss charges nothing and banks nothing — see the module docstring.
    """
    gain = np.maximum(0.0, preferential_income)
    start = np.maximum(0.0, ordinary_taxable)
    return tax_on_slice(_preferential_ladder(cfg, status), start=start, end=start + gain)


def net_investment_income_tax(
    net_investment_income: np.ndarray,
    *,
    modified_agi: np.ndarray,
    status: FilingStatus,
    cfg: USTaxConfig,
) -> np.ndarray:
    """§ 1411, charged on the lesser of two amounts.

    3.8 % of net investment income or of the excess of modified AGI over the threshold,
    whichever is smaller. The threshold is `FixedMoney` and never indexed, so a
    projection forty years out still charges against today's nominal dollars — which is
    the point, and the whole reason that unit exists. Charged uncredited; see above.
    """
    threshold = float(cfg.by_filing_status("niit_threshold", status))
    excess = np.maximum(0.0, modified_agi - threshold)
    charged_on = np.minimum(np.maximum(0.0, net_investment_income), excess)
    return charged_on * float(cfg.niit_rate)
