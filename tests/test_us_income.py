"""US federal ordinary tax: the seven-band ladder, filing status, and the FEIE."""

from decimal import Decimal
from typing import get_args

import numpy as np
import pytest

from vuurtoren.domain import FilingStatus
from vuurtoren.tax.config import defaults_for
from vuurtoren.tax.us.config import USTaxConfig
from vuurtoren.tax.us.federal.income import (
    bracket_tax,
    excluded_earned_income,
    ordinary_tax,
    taxable_income,
)

CFG = defaults_for("US", 2026, expect=USTaxConfig)


def _one(x: float) -> np.ndarray:
    """A one-run array — the deterministic projection's shape (invariant #6)."""
    return np.array([x])


def test_every_domain_filing_status_maps_to_a_figure_suffix() -> None:
    """Every figure family resolves for every status the domain type allows.

    Driven by `domain.FilingStatus` rather than by anything in `tax/us`, so adding a
    filing status to the domain without giving it a home in the figures fails here — and
    `by_filing_status` builds a field name, so a mistyped family fails here too, rather
    than in a projection forty years out.
    """
    families = [
        "standard_deduction",
        *[f"ordinary_bracket_{n}_to" for n in range(1, 7)],
        "ltcg_zero_rate_top",
        "ltcg_fifteen_rate_top",
        "niit_threshold",
    ]
    for figure in families:
        for status in get_args(FilingStatus):
            assert CFG.by_filing_status(figure, status) > 0, f"{figure} / {status}"


def test_an_unknown_figure_family_fails_by_name() -> None:
    """And the message says which field it looked for."""
    with pytest.raises(KeyError, match="standard_deducton"):
        CFG.by_filing_status("standard_deducton", "married_filing_jointly")


def test_the_ladder_is_marginal_not_a_cliff() -> None:
    """One dollar past a threshold is taxed at the new rate, not the whole income."""
    top_of_band_2 = float(CFG.ordinary_bracket_2_to_single)

    step = bracket_tax(_one(top_of_band_2 + 1), status="single", cfg=CFG) - bracket_tax(
        _one(top_of_band_2), status="single", cfg=CFG
    )

    assert step == pytest.approx(float(CFG.ordinary_rate_3))


def test_the_top_band_splits_between_single_and_married_filing_separately() -> None:
    """At $500,000 a single filer is still in the 35 % band and an MFS filer is not.

    The main case is a US citizen married to a non-US spouse, who files MFS. Reusing
    the single schedule for them understates the marginal rate exactly here.
    """
    at_500k = _one(500_000.0)
    a_dollar_more = _one(500_001.0)

    single = bracket_tax(a_dollar_more, status="single", cfg=CFG) - bracket_tax(
        at_500k, status="single", cfg=CFG
    )
    mfs = bracket_tax(a_dollar_more, status="married_filing_separately", cfg=CFG) - bracket_tax(
        at_500k, status="married_filing_separately", cfg=CFG
    )

    assert single == pytest.approx(float(CFG.ordinary_rate_6))  # 35 %
    assert mfs == pytest.approx(float(CFG.ordinary_rate_7))  # 37 %


def test_a_salary_inside_the_feie_limit_is_taxed_at_nothing() -> None:
    """The whole point of the section 911 election, and the common expat case."""
    salary = _one(float(CFG.feie_limit) - 10_000)

    charged = ordinary_tax(
        taxable_income(salary, _one(0.0), status="single", cfg=CFG),
        excluded=excluded_earned_income(salary, cfg=CFG),
        status="single",
        cfg=CFG,
    )

    assert charged == pytest.approx(0.0)


def test_the_exclusion_stops_at_the_limit() -> None:
    """Earnings past the limit are not excluded — section 911(b)(2)(D)(i) caps it."""
    assert excluded_earned_income(_one(1_000_000.0), cfg=CFG) == pytest.approx(
        float(CFG.feie_limit)
    )
    assert excluded_earned_income(_one(50_000.0), cfg=CFG) == pytest.approx(50_000.0)


def test_income_above_the_limit_is_taxed_at_the_rate_it_would_have_faced() -> None:
    """Section 911(f): the exclusion lowers the base, never the bracket.

    A salary $50,000 above the limit is not taxed as if it were a $50,000 salary. The
    stacking rule puts the excess on top of the excluded amount, so the first dollar of
    it meets the marginal rate a ~$183,000 earner faces. Ignoring this understates the
    tax substantially, which is why it is modelled rather than noted.
    """
    salary = _one(float(CFG.feie_limit) + 50_000)
    excluded = excluded_earned_income(salary, cfg=CFG)
    taxable = taxable_income(salary, _one(0.0), status="single", cfg=CFG)

    stacked = ordinary_tax(taxable, excluded=excluded, status="single", cfg=CFG)
    from_the_bottom = bracket_tax(taxable, status="single", cfg=CFG)

    assert stacked > from_the_bottom
    assert stacked == pytest.approx(
        bracket_tax(taxable + excluded, status="single", cfg=CFG)
        - bracket_tax(excluded, status="single", cfg=CFG)
    )


def test_the_standard_deduction_comes_off_the_base() -> None:
    """And the base never goes below zero — a small income is untaxed, not a refund."""
    taxable = taxable_income(_one(0.0), _one(50_000.0), status="married_filing_jointly", cfg=CFG)
    under_the_deduction = taxable_income(
        _one(0.0), _one(1_000.0), status="married_filing_jointly", cfg=CFG
    )

    assert taxable == pytest.approx(50_000.0 - float(CFG.standard_deduction_mfj))
    assert under_the_deduction == pytest.approx(0.0)


def test_the_ladder_is_vectorised_over_runs() -> None:
    """Invariant #6: the engine is `(n_runs,)` arrays throughout, never a scalar path."""
    incomes = np.array([0.0, 50_000.0, 500_000.0])

    charged = bracket_tax(incomes, status="married_filing_jointly", cfg=CFG)

    assert charged.shape == (3,)
    assert charged[0] == pytest.approx(0.0)
    assert charged[1] < charged[2]


def test_a_negative_base_is_not_a_refund() -> None:
    """A loss year owes nothing; it does not generate a credit here."""
    assert bracket_tax(_one(-5_000.0), status="single", cfg=CFG) == pytest.approx(0.0)


def test_indexing_moves_the_bands_under_the_same_rates() -> None:
    """A projection forty years out runs the same ladder on indexed thresholds.

    $500,000 is an MFS filer's top band today and its fifth band once the thresholds have
    doubled — which is the whole reason the bands are `Money` and the rates are not.
    """
    later = CFG.indexed(Decimal(2))

    def marginal(cfg: USTaxConfig) -> np.ndarray:
        """The rate the 500,001st dollar meets, under `cfg`'s thresholds."""
        return bracket_tax(
            _one(500_001.0), status="married_filing_separately", cfg=cfg
        ) - bracket_tax(_one(500_000.0), status="married_filing_separately", cfg=cfg)

    assert later.ordinary_bracket_6_to_mfs == CFG.ordinary_bracket_6_to_mfs * 2
    assert later.ordinary_rate_7 == CFG.ordinary_rate_7
    assert marginal(CFG) == pytest.approx(float(CFG.ordinary_rate_7))
    assert marginal(later) == pytest.approx(float(CFG.ordinary_rate_5))
