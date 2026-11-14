"""Differential checks for federal schedules and state carried between years."""

from importlib import import_module
from typing import TYPE_CHECKING

import numpy as np
from hypothesis import given, strategies as st
from numpy.testing import assert_allclose

if TYPE_CHECKING:
    from vuurtoren.domain import FilingStatus
from vuurtoren.tax.config import defaults_for
from vuurtoren.tax.us.config import USTaxConfig
from vuurtoren.tax.us.federal import ftc, income, investment, pfic

core = import_module("vuurtoren_core")

_AMOUNTS = st.lists(st.integers(-100_000_000, 100_000_000), min_size=1, max_size=20)
_STATUS = st.sampled_from(["single", "married_filing_separately", "married_filing_jointly"])


def check(actual: object, expected: np.ndarray) -> None:
    """One microcent permits the same float64 expressions' arithmetic order."""
    assert_allclose(np.asarray(actual), expected, rtol=1e-14, atol=1e-8, strict=True)


@given(amounts=_AMOUNTS, status=_STATUS)
def test_schedules(amounts: list[int], status: FilingStatus) -> None:
    """Ordinary, exclusion, deduction, preferential and NIIT schedules agree."""
    cfg = defaults_for("US", 2026, expect=USTaxConfig)
    a = np.asarray(amounts, dtype=float) / 100
    b = a[::-1].copy()
    check(core.us_bracket_tax(a, status, cfg), income.bracket_tax(a, status=status, cfg=cfg))
    check(core.us_excluded_earned_income(a, cfg), income.excluded_earned_income(a, cfg=cfg))
    check(
        core.us_taxable_income(a, b, status, cfg),
        income.taxable_income(a, b, status=status, cfg=cfg),
    )
    check(
        core.us_unused_deduction(a, b, status, cfg),
        income.unused_deduction(a, b, status=status, cfg=cfg),
    )
    check(
        core.us_ordinary_tax(a, b, status, cfg),
        income.ordinary_tax(a, excluded=b, status=status, cfg=cfg),
    )
    check(
        core.us_preferential_tax(a, b, status, cfg),
        investment.preferential_tax(a, ordinary_taxable=b, status=status, cfg=cfg),
    )
    check(
        core.us_niit(a, b, status, cfg),
        investment.net_investment_income_tax(a, modified_agi=b, status=status, cfg=cfg),
    )


@given(amounts=_AMOUNTS, years=st.integers(0, 12))
def test_credit_and_pfic(amounts: list[int], years: int) -> None:
    """Each vintage ages independently; a PFIC loss is capped by prior inclusions."""
    a = np.asarray(amounts, dtype=float) / 100
    b = np.abs(a[::-1])
    total = a + b
    bank = tuple(np.maximum(a / (n + 1), 0.0) for n in range(years))
    check(
        core.us_credit_limitation(a, b, total),
        ftc.limitation(a, foreign_source_income=b, total_income=total),
    )
    expected, carry = ftc.apply_credit(
        a, foreign_tax_paid=b, foreign_source_income=b, total_income=total, carryforward=bank
    )
    actual, actual_carry = core.us_apply_credit(a, b, b, total, bank)
    check(actual, expected)
    assert len(actual_carry) == len(carry)
    for actual_vintage, vintage in zip(actual_carry, carry, strict=True):
        check(actual_vintage, vintage)
    expected_inclusion, expected_pool = pfic.mark_to_market_inclusion(a, unreversed_inclusions=b)
    actual_inclusion, actual_pool = core.us_pfic_inclusion(a, b)
    check(actual_inclusion, expected_inclusion)
    check(actual_pool, expected_pool)
    check(core.us_pfic_sale_gain(a, b), pfic.sale_gain_after_step_up(a, unreversed_inclusions=b))
