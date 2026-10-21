"""US federal investment tax: preferential rates stacked on ordinary income, and NIIT."""

from decimal import Decimal

import numpy as np
import pytest

from vuurtoren.tax.config import defaults_for
from vuurtoren.tax.us.config import USTaxConfig
from vuurtoren.tax.us.federal.investment import net_investment_income_tax, preferential_tax

CFG = defaults_for("US", 2026, expect=USTaxConfig)


def _one(x: float) -> np.ndarray:
    return np.array([x])


def test_a_gain_entirely_inside_the_zero_band_is_untaxed() -> None:
    """A modest gain on top of a modest income costs nothing federally."""
    charged = preferential_tax(
        _one(10_000.0),
        ordinary_taxable=_one(20_000.0),
        status="single",
        cfg=CFG,
    )

    assert charged == pytest.approx(0.0)


def test_the_thresholds_read_total_taxable_income_not_the_gain_alone() -> None:
    """The part that is easy to get wrong, and the reason this is not a flat rate.

    The same $10,000 gain is untaxed for a low earner and taxed at 15 % for someone whose
    ordinary income already fills the zero band. Reading the threshold against the gain
    alone would make every gain in the app untaxed.
    """
    small_income = preferential_tax(
        _one(10_000.0), ordinary_taxable=_one(20_000.0), status="single", cfg=CFG
    )
    large_income = preferential_tax(
        _one(10_000.0), ordinary_taxable=_one(200_000.0), status="single", cfg=CFG
    )

    assert small_income == pytest.approx(0.0)
    assert large_income == pytest.approx(10_000.0 * float(CFG.ltcg_rate_2))


def test_a_gain_straddling_a_threshold_is_split_between_the_bands() -> None:
    """Marginal, not a cliff: only the part above the threshold meets the higher rate."""
    zero_top = float(CFG.ltcg_zero_rate_top_single)
    ordinary = zero_top - 5_000.0

    charged = preferential_tax(
        _one(10_000.0), ordinary_taxable=_one(ordinary), status="single", cfg=CFG
    )

    assert charged == pytest.approx(5_000.0 * float(CFG.ltcg_rate_2))


def test_the_top_band_charges_twenty_percent() -> None:
    """A gain landing wholly above the 15 % ceiling meets the top rate."""
    fifteen_top = float(CFG.ltcg_fifteen_rate_top_mfj)

    charged = preferential_tax(
        _one(100_000.0),
        ordinary_taxable=_one(fifteen_top),
        status="married_filing_jointly",
        cfg=CFG,
    )

    assert charged == pytest.approx(100_000.0 * float(CFG.ltcg_rate_3))


def test_a_loss_is_not_a_refund() -> None:
    """Capital loss carryforward is not modelled here — a negative gain charges nothing."""
    charged = preferential_tax(
        _one(-50_000.0),
        ordinary_taxable=_one(300_000.0),
        status="married_filing_separately",
        cfg=CFG,
    )

    assert charged == pytest.approx(0.0)


def test_niit_does_not_bite_below_the_threshold() -> None:
    """A dollar under the threshold and a large portfolio still charges nothing."""
    charged = net_investment_income_tax(
        _one(50_000.0),
        modified_agi=_one(float(CFG.niit_threshold_single) - 1),
        status="single",
        cfg=CFG,
    )

    assert charged == pytest.approx(0.0)


def test_niit_charges_the_lesser_of_the_two_amounts() -> None:
    """Section 1411(a)(1) charges the lesser of the two amounts.

    So a large portfolio gain on a barely-over AGI is charged on the excess, and a small
    gain on a huge AGI is charged on the gain. Taking either one alone would be wrong in
    one of these two directions.
    """
    threshold = float(CFG.niit_threshold_mfj)
    rate = float(CFG.niit_rate)

    excess_binds = net_investment_income_tax(
        _one(500_000.0),
        modified_agi=_one(threshold + 10_000.0),
        status="married_filing_jointly",
        cfg=CFG,
    )
    income_binds = net_investment_income_tax(
        _one(10_000.0),
        modified_agi=_one(threshold + 500_000.0),
        status="married_filing_jointly",
        cfg=CFG,
    )

    assert excess_binds == pytest.approx(10_000.0 * rate)
    assert income_binds == pytest.approx(10_000.0 * rate)


def test_the_mfs_niit_threshold_is_half_the_joint_one() -> None:
    """$125,000, not $250,000 — the trap for a US citizen married to a non-US spouse."""
    assert CFG.niit_threshold_mfs == Decimal(125_000)
    assert CFG.niit_threshold_mfj == Decimal(250_000)


def test_the_niit_threshold_is_still_nominal_forty_years_out() -> None:
    """Section 1411(b) fixes it, so a 2066 projection charges NIIT on the same $200,000.

    This is the trap the whole `FixedMoney` unit exists for: indexing it would push the
    threshold beyond incomes that in reality drift across it, understating US tax by more
    every year of the horizon.
    """
    later = CFG.indexed(Decimal("2.2"))
    agi = _one(float(CFG.niit_threshold_single) + 100_000.0)

    now = net_investment_income_tax(_one(100_000.0), modified_agi=agi, status="single", cfg=CFG)
    forty_years_on = net_investment_income_tax(
        _one(100_000.0), modified_agi=agi, status="single", cfg=later
    )

    assert later.ltcg_zero_rate_top_single > CFG.ltcg_zero_rate_top_single
    assert forty_years_on == pytest.approx(now)


def test_both_charges_are_vectorised_over_runs() -> None:
    """Invariant #6 — the Monte Carlo layer is this same code with more runs."""
    gains = np.array([0.0, 10_000.0, 100_000.0])
    ordinary = np.full(3, 200_000.0)

    preferential = preferential_tax(gains, ordinary_taxable=ordinary, status="single", cfg=CFG)
    niit = net_investment_income_tax(gains, modified_agi=ordinary + gains, status="single", cfg=CFG)

    assert preferential.shape == (3,)
    assert niit.shape == (3,)
    assert preferential[0] == pytest.approx(0.0)
    assert niit[2] > niit[1] > niit[0]
